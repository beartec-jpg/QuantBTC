#!/usr/bin/env python3
"""
QuantumBTC 1000-Transaction Stress Test
========================================
Creates 10 wallets, funds them, executes 1000 PQC hybrid transactions
between random wallet pairs, mines them into blocks, and produces
a comprehensive statistical report.
"""

import subprocess
import json
import sys
import time
import random
import os
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────
BITCOIND = os.environ.get("BITCOIND", "build-fresh/src/bitcoind")
CLI = os.environ.get("CLI", "build-fresh/src/bitcoin-cli")
CHAIN = "qbtctestnet"
NUM_WALLETS = 10
NUM_TXS = 1000
BATCH_SIZE = 50       # txs per mining batch
FUND_AMOUNT = 50.0    # QBTC per wallet
SEND_MIN = 0.001
SEND_MAX = 0.5

# ── Helpers ────────────────────────────────────────────────────────────
def cli(*args, wallet=None):
    cmd = [CLI, f"-{CHAIN}"]
    if wallet:
        cmd.append(f"-rpcwallet={wallet}")
    cmd.extend(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"CLI error: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()

def cli_json(*args, wallet=None):
    return json.loads(cli(*args, wallet=wallet))

def mine(n, addr):
    return cli_json("generatetoaddress", str(n), addr)

# ── Stats accumulators ─────────────────────────────────────────────────
tx_sizes = []       # raw size in bytes
tx_vsizes = []      # virtual size in vB
tx_weights = []     # weight units
tx_fees = []        # fee in BTC
tx_times = []       # wall-clock seconds per tx
tx_witness_elems = []
tx_input_counts = []
tx_output_counts = []
wallet_send_count = defaultdict(int)
wallet_recv_count = defaultdict(int)
blocks_mined = 0
txs_confirmed = 0
errors = []

def percentile(data, p):
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (s[c] - s[f]) * (k - f)

def mean(data):
    return sum(data) / len(data) if data else 0

def median(data):
    return percentile(data, 50)

# ── Main ───────────────────────────────────────────────────────────────
def main():
    random.seed(42)
    print("=" * 70)
    print(" QuantumBTC 1000-Transaction Stress Test")
    print("=" * 70)
    global blocks_mined, txs_confirmed

    # ── 1. Check node ──────────────────────────────────────────────────
    print("\n[1/6] Checking node status...")
    try:
        info = cli_json("getblockchaininfo")
    except Exception:
        print("  Node not running. Starting...")
        subprocess.Popen(
            [BITCOIND, f"-{CHAIN}", "-daemon", "-fallbackfee=0.0001",
             "-txindex=1", "-server=1", "-listen=1", "-printtoconsole=0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(30):
            time.sleep(1)
            try:
                info = cli_json("getblockchaininfo")
                break
            except Exception:
                pass
        else:
            print("  FATAL: Could not start node")
            sys.exit(1)
    start_height = info["blocks"]
    print(f"  Node running: chain={info['chain']}, height={start_height}, "
          f"pqc={info['pqc']}, dag={info['dagmode']}")

    # ── 2. Create 10 wallets ───────────────────────────────────────────
    print(f"\n[2/6] Creating {NUM_WALLETS} wallets...")
    wallets = []
    for i in range(NUM_WALLETS):
        name = f"w{i}"
        try:
            cli("createwallet", name)
        except RuntimeError:
            try:
                cli("loadwallet", name)
            except RuntimeError:
                pass  # already loaded
        addr = cli("getnewaddress", "", "bech32", wallet=name)
        wallets.append({"name": name, "addr": addr, "addrs": [addr]})
        print(f"  {name}: {addr}")

    # Generate extra receiving addresses per wallet
    for w in wallets:
        for _ in range(4):
            a = cli("getnewaddress", "", "bech32", wallet=w["name"])
            w["addrs"].append(a)

    # ── 3. Fund wallets ────────────────────────────────────────────────
    print(f"\n[3/6] Funding wallets ({FUND_AMOUNT} QBTC each)...")
    miner_addr = wallets[0]["addrs"][0]

    # Mine initial blocks to get mature coins
    print("  Mining 220 blocks for coinbase maturity...")
    mine(220, miner_addr)
    blocks_mined += 220

    # Distribute funds to all wallets (in batches to avoid UTXO shortage)
    print("  Distributing funds...")
    for w in wallets[1:]:
        try:
            cli("sendtoaddress", w["addr"], str(FUND_AMOUNT), wallet=wallets[0]["name"])
        except RuntimeError as e:
            errors.append(f"Fund {w['name']}: {e}")

    # Mine to confirm funding txs + create more mature coinbase
    mine(10, miner_addr)
    blocks_mined += 10

    # Second funding round — top up any that failed
    for w in wallets[1:]:
        bal = float(cli("getbalance", wallet=w["name"]))
        if bal < FUND_AMOUNT * 0.5:
            try:
                cli("sendtoaddress", w["addr"], str(FUND_AMOUNT), wallet=wallets[0]["name"])
            except RuntimeError as e:
                errors.append(f"Fund2 {w['name']}: {e}")

    mine(10, miner_addr)
    blocks_mined += 10

    # Check balances
    total_funded = 0
    for w in wallets:
        bal = float(cli("getbalance", wallet=w["name"]))
        total_funded += bal
        print(f"  {w['name']}: {bal:.4f} QBTC")

    # ── 4. Execute 1000 transactions ───────────────────────────────────
    print(f"\n[4/6] Executing {NUM_TXS} PQC transactions...")
    t_start_all = time.time()
    batch_count = 0
    succeeded = 0
    failed = 0

    for tx_i in range(NUM_TXS):
        # Pick random sender and receiver (different wallets)
        sender_idx = random.randint(0, NUM_WALLETS - 1)
        receiver_idx = sender_idx
        while receiver_idx == sender_idx:
            receiver_idx = random.randint(0, NUM_WALLETS - 1)

        sender = wallets[sender_idx]
        receiver = wallets[receiver_idx]
        recv_addr = random.choice(receiver["addrs"])
        amount = round(random.uniform(SEND_MIN, SEND_MAX), 8)

        t0 = time.time()
        try:
            txid = cli("sendtoaddress", recv_addr, f"{amount:.8f}",
                        wallet=sender["name"])
            dt = time.time() - t0
            tx_times.append(dt)
            wallet_send_count[sender["name"]] += 1
            wallet_recv_count[receiver["name"]] += 1

            # Get tx details from mempool
            try:
                txinfo = cli_json("getrawtransaction", txid, "true")
                tx_sizes.append(txinfo["size"])
                tx_vsizes.append(txinfo["vsize"])
                tx_weights.append(txinfo["weight"])
                tx_input_counts.append(len(txinfo["vin"]))
                tx_output_counts.append(len(txinfo["vout"]))

                # Count witness elements on first input
                wit = txinfo["vin"][0].get("txinwitness", [])
                tx_witness_elems.append(len(wit))

                # Calculate fee
                if "fee" in txinfo:
                    tx_fees.append(abs(txinfo["fee"]))
                else:
                    # try getmempoolentry
                    try:
                        mpe = cli_json("getmempoolentry", txid)
                        fee_btc = mpe.get("fees", {}).get("base", 0)
                        tx_fees.append(fee_btc)
                    except Exception:
                        pass
            except Exception:
                pass

            succeeded += 1
        except RuntimeError as e:
            failed += 1
            dt = time.time() - t0
            err_msg = str(e)
            if "Insufficient funds" not in err_msg:
                errors.append(f"tx {tx_i}: {err_msg[:120]}")

        # Mine a batch every BATCH_SIZE txs to keep UTXOs flowing
        batch_count += 1
        if batch_count >= BATCH_SIZE or (failed > succeeded and batch_count >= 10):
            try:
                mine(1, miner_addr)
                blocks_mined += 1
            except Exception:
                pass
            batch_count = 0

        # Progress indicator
        if (tx_i + 1) % 100 == 0:
            elapsed = time.time() - t_start_all
            rate = (tx_i + 1) / elapsed
            print(f"  [{tx_i+1}/{NUM_TXS}] ok={succeeded} fail={failed} "
                  f"rate={rate:.1f} tx/s elapsed={elapsed:.1f}s")

    t_total = time.time() - t_start_all

    # Mine remaining
    mine(6, miner_addr)
    blocks_mined += 6

    # ── 5. Collect final stats ─────────────────────────────────────────
    print(f"\n[5/6] Collecting statistics...")
    final_info = cli_json("getblockchaininfo")
    final_height = final_info["blocks"]
    mempool = cli_json("getmempoolinfo")

    # Get debug.log PQC stats
    log_path = os.path.expanduser(f"~/.bitcoin/{CHAIN}/debug.log")
    dil_created = 0
    dil_verified = 0
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            for line in f:
                if "Dilithium signature created" in line:
                    dil_created += 1
                if "Dilithium signature verified" in line:
                    dil_verified += 1

    # Final balances
    final_balances = {}
    for w in wallets:
        final_balances[w["name"]] = float(cli("getbalance", wallet=w["name"]))

    # Count confirmed transactions by scanning blocks
    pqc_txs_in_blocks = 0
    pqc_witness_in_blocks = 0
    block_sizes = []
    block_weights_list = []
    block_tx_counts = []
    for h in range(max(1, start_height + 1), final_height + 1):
        try:
            bh = cli("getblockhash", str(h))
            blk = cli_json("getblock", bh, "1")
            ntx = blk.get("nTx", len(blk.get("tx", [])))
            block_tx_counts.append(ntx)
            block_sizes.append(blk.get("size", 0))
            block_weights_list.append(blk.get("weight", 0))
            if ntx > 1:
                pqc_txs_in_blocks += ntx - 1  # subtract coinbase
        except Exception:
            pass
    txs_confirmed = pqc_txs_in_blocks

    # ── 6. Report ──────────────────────────────────────────────────────
    print(f"\n[6/6] Generating report...")
    print("\n" + "=" * 70)
    print(" QUANTUMBTC 1000-TRANSACTION STRESS TEST REPORT")
    print("=" * 70)

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  NETWORK CONFIGURATION                                             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Chain:              {final_info['chain']:<47}║
║  PQC Mode:           {'hybrid (ECDSA + ML-DSA-44)':<47}║
║  DAG Mode:           {str(final_info['dagmode']):<47}║
║  GHOSTDAG K:         {final_info['ghostdag_k']:<47}║
║  Ticker:             {final_info.get('ticker', 'QBTC'):<47}║
║  DAG Tips:           {final_info.get('dag_tips', 0):<47}║
╚══════════════════════════════════════════════════════════════════════╝""")

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  TRANSACTION SUMMARY                                               ║
╠══════════════════════════════════════════════════════════════════════╣
║  Target:             {NUM_TXS:<47}║
║  Succeeded:          {succeeded:<47}║
║  Failed:             {failed:<47}║
║  Success Rate:       {f'{succeeded/NUM_TXS*100:.1f}%':<47}║
║  Total Time:         {f'{t_total:.1f} seconds':<47}║
║  Throughput:         {f'{succeeded/t_total:.2f} tx/sec':<47}║
║  Avg Latency:        {f'{mean(tx_times)*1000:.1f} ms/tx (RPC call)':<47}║
╚══════════════════════════════════════════════════════════════════════╝""")

    if tx_vsizes:
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  TRANSACTION SIZE ANALYSIS (PQC Hybrid Witness)                    ║
╠══════════════════════════════════════════════════════════════════════╣
║                     Min        Mean       Median     Max            ║
║  Raw Size (B):     {min(tx_sizes):>6}     {mean(tx_sizes):>8.0f}     {median(tx_sizes):>8.0f}     {max(tx_sizes):>6}    ║
║  Vsize (vB):       {min(tx_vsizes):>6}     {mean(tx_vsizes):>8.0f}     {median(tx_vsizes):>8.0f}     {max(tx_vsizes):>6}    ║
║  Weight (WU):      {min(tx_weights):>6}     {mean(tx_weights):>8.0f}     {median(tx_weights):>8.0f}     {max(tx_weights):>6}    ║
╠══════════════════════════════════════════════════════════════════════╣
║  P5 Vsize:         {percentile(tx_vsizes, 5):>8.0f} vB                                  ║
║  P25 Vsize:        {percentile(tx_vsizes, 25):>8.0f} vB                                  ║
║  P75 Vsize:        {percentile(tx_vsizes, 75):>8.0f} vB                                  ║
║  P95 Vsize:        {percentile(tx_vsizes, 95):>8.0f} vB                                  ║
║  P99 Vsize:        {percentile(tx_vsizes, 99):>8.0f} vB                                  ║
╚══════════════════════════════════════════════════════════════════════╝""")

    if tx_fees:
        fee_sats = [f * 1e8 for f in tx_fees]
        fee_rates = [f * 1e8 / v if v > 0 else 0 for f, v in zip(tx_fees, tx_vsizes[:len(tx_fees)])]
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  FEE ANALYSIS                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║                     Min        Mean       Median     Max            ║
║  Fee (sats):       {min(fee_sats):>6.0f}     {mean(fee_sats):>8.0f}     {median(fee_sats):>8.0f}     {max(fee_sats):>6.0f}    ║
║  Rate (sat/vB):    {min(fee_rates):>6.1f}     {mean(fee_rates):>8.1f}     {median(fee_rates):>8.1f}     {max(fee_rates):>6.1f}    ║
║  Total Fees:       {sum(fee_sats):>10.0f} sats ({sum(tx_fees):.8f} QBTC)              ║
╚══════════════════════════════════════════════════════════════════════╝""")

    if tx_input_counts:
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  INPUT/OUTPUT ANALYSIS                                             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Avg Inputs/tx:     {mean(tx_input_counts):>6.2f}                                        ║
║  Avg Outputs/tx:    {mean(tx_output_counts):>6.2f}                                        ║
║  Max Inputs:        {max(tx_input_counts):>6}                                        ║
║  Max Outputs:       {max(tx_output_counts):>6}                                        ║
║  1-input txs:       {sum(1 for x in tx_input_counts if x == 1):>6} ({sum(1 for x in tx_input_counts if x == 1)/len(tx_input_counts)*100:.1f}%)                                  ║
║  Multi-input txs:   {sum(1 for x in tx_input_counts if x > 1):>6} ({sum(1 for x in tx_input_counts if x > 1)/len(tx_input_counts)*100:.1f}%)                                  ║
╚══════════════════════════════════════════════════════════════════════╝""")

    if tx_witness_elems:
        pqc_4elem = sum(1 for x in tx_witness_elems if x == 4)
        non_pqc = sum(1 for x in tx_witness_elems if x != 4)
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  PQC WITNESS ANALYSIS                                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  4-element (PQC hybrid):  {pqc_4elem:>6}  ({pqc_4elem/len(tx_witness_elems)*100:.1f}%)                          ║
║  Other:                   {non_pqc:>6}  ({non_pqc/len(tx_witness_elems)*100:.1f}%)                          ║
║  Witness Breakdown (per PQC input):                                ║
║    [0] ECDSA sig:         ~71 bytes  (secp256k1)                   ║
║    [1] EC pubkey:          33 bytes  (compressed)                  ║
║    [2] Dilithium sig:   2,420 bytes  (ML-DSA-44)                   ║
║    [3] Dilithium pk:    1,312 bytes  (ML-DSA-44)                   ║
╚══════════════════════════════════════════════════════════════════════╝""")

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  BLOCKCHAIN SUMMARY                                                ║
╠══════════════════════════════════════════════════════════════════════╣
║  Start Height:      {start_height:<47}║
║  Final Height:      {final_height:<47}║
║  Blocks Mined:      {blocks_mined:<47}║
║  PQC Txs Confirmed: {txs_confirmed:<47}║
║  Mempool Size:      {mempool.get('size', 0):<47}║
║  Chain Size:        {f'{final_info["size_on_disk"] / 1024 / 1024:.2f} MB':<47}║
╚══════════════════════════════════════════════════════════════════════╝""")

    if block_tx_counts:
        non_empty = [c for c in block_tx_counts if c > 1]
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  BLOCK ANALYSIS                                                    ║
╠══════════════════════════════════════════════════════════════════════╣
║  Total Blocks:      {len(block_tx_counts):<47}║
║  Non-empty Blocks:  {len(non_empty):<47}║
║  Avg Txs/Block:     {f'{mean(non_empty):.1f} (non-empty blocks only)' if non_empty else 'N/A':<47}║
║  Max Txs/Block:     {max(block_tx_counts) if block_tx_counts else 0:<47}║
║  Max Block Size:    {f'{max(block_sizes)/1024:.1f} KB' if block_sizes else 'N/A':<47}║
║  Max Block Weight:  {f'{max(block_weights_list)/1000:.1f} KWU' if block_weights_list else 'N/A':<47}║
║  Avg Block Size:    {f'{mean(block_sizes)/1024:.1f} KB' if block_sizes else 'N/A':<47}║
╚══════════════════════════════════════════════════════════════════════╝""")

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  DILITHIUM CRYPTOGRAPHY STATS                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║  Signatures Created:  {dil_created:<45}║
║  Signatures Verified: {dil_verified:<45}║
║  Verify/Create Ratio: {f'{dil_verified/dil_created:.2f}x' if dil_created else 'N/A':<45}║
╚══════════════════════════════════════════════════════════════════════╝""")

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  WALLET ACTIVITY (10 Wallets)                                      ║
╠══════════════════════════╦═════════╦═════════╦══════════════════════╣
║  Wallet                  ║  Sent   ║  Recv   ║  Final Balance       ║
╠══════════════════════════╬═════════╬═════════╬══════════════════════╣""")
    for w in wallets:
        n = w["name"]
        s = wallet_send_count[n]
        r = wallet_recv_count[n]
        b = final_balances.get(n, 0)
        print(f"║  {n:<24}║  {s:>5}  ║  {r:>5}  ║  {b:>12.4f} QBTC   ║")
    total_bal = sum(final_balances.values())
    total_sent = sum(wallet_send_count.values())
    total_recv = sum(wallet_recv_count.values())
    print(f"""╠══════════════════════════╬═════════╬═════════╬══════════════════════╣
║  TOTAL                   ║  {total_sent:>5}  ║  {total_recv:>5}  ║  {total_bal:>12.4f} QBTC   ║
╚══════════════════════════╩═════════╩═════════╩══════════════════════╝""")

    if errors:
        print(f"\n  Errors ({len(errors)} total):")
        # Show first 10 unique errors
        seen = set()
        shown = 0
        for e in errors:
            short = e[:100]
            if short not in seen:
                seen.add(short)
                print(f"    - {short}")
                shown += 1
                if shown >= 10:
                    print(f"    ... and {len(errors) - shown} more")
                    break

    # ── Data bandwidth calculation ─────────────────────────────────────
    if tx_sizes:
        total_bytes = sum(tx_sizes)
        total_witness_bytes = sum(tx_sizes) - sum(tx_vsizes)  # rough
        print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  BANDWIDTH / STORAGE IMPACT                                        ║
╠══════════════════════════════════════════════════════════════════════╣
║  Total TX Data:     {f'{total_bytes / 1024 / 1024:.2f} MB':<47}║
║  PQC Overhead:      {f'~{(mean(tx_sizes) - 141 * mean(tx_input_counts)) / mean(tx_sizes) * 100:.0f}% of tx data is PQC witness':<47}║
║  Classical Equiv:   {f'~{sum(tx_input_counts) * 141 / 1024 / 1024:.2f} MB (without PQC)':<47}║
║  PQC Multiplier:    {f'{mean(tx_sizes) / (141 * mean(tx_input_counts)):.1f}x larger than classical P2WPKH':<47}║
╚══════════════════════════════════════════════════════════════════════╝""")

    print("\n" + "=" * 70)
    print(" TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
