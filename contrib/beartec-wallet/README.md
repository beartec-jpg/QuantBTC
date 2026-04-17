# BearTec Wallet – QuantumBTC Integration

## Quick Start

```bash
pip install ecdsa  # required for offline signing
cd /workspaces/QuantBTC/contrib/beartec-wallet
python3 qbtc_wallet.py   # run self-test
```

## Architecture

```
BearTec Wallet
├── Existing BTC/ETH/etc chains
└── QuantumBTC (QBTC)              ← new chain
    ├── Key Generation               qbtc_wallet.QBTCKeyPair
    │   ├── ECDSA (secp256k1)        HMAC-SHA512(seed, "QBTC-ECDSA" || idx)
    │   └── Dilithium2 (ML-DSA-44)   HMAC-SHA512(seed, "QBTC-PQC"   || idx)
    │       (ECDSA and Dilithium derived INDEPENDENTLY from master seed)
    ├── Address                       qbtct1... (Bech32 P2WPKH)
    ├── Transaction Signing           4-element witness (hybrid PQC)
    └── 2-of-3 Seed Splitting        Shamir over 64-byte master seed
```

## 1. Generate PQC + ECDSA Keypairs from Seed

```python
from qbtc_wallet import QBTCKeyPair

# From your existing BIP-39 master seed (64 bytes from mnemonic)
master_seed = bytes.fromhex("your_bip39_seed_hex_here")

# Derive QBTC keypair (index 0 = first account)
kp = QBTCKeyPair.from_seed(master_seed, path_index=0)

# ECDSA and Dilithium are derived INDEPENDENTLY via domain separation:
#   ecdsa_key = HMAC-SHA512(seed, "QBTC-ECDSA" || index)[0:32]
#   pqc_seed  = HMAC-SHA512(seed, "QBTC-PQC"   || index)[0:32]
# Breaking ECDSA does NOT compromise the Dilithium key.

print(kp.address())                        # qbtct1q7x...
print(kp.ecdsa.pubkey_compressed.hex())     # 02abc...
# print(kp.dilithium.public_key[:32].hex())  # requires liboqs-python
```

## 2. Create a Valid qbtct1... Bech32 Address

```python
from qbtc_wallet import QBTCKeyPair, QBTC_TESTNET_HRP, QBTC_MAINNET_HRP

kp = QBTCKeyPair.generate()

testnet_addr = kp.address(QBTC_TESTNET_HRP)  # qbtct1q...
mainnet_addr = kp.address(QBTC_MAINNET_HRP)  # qbtc1q...

# Address = Bech32(HRP, witness_version=0, HASH160(compressed_ecdsa_pubkey))
# Same as BTC P2WPKH, just different HRP.
```

## 3. Sign a Transaction Using Hybrid PQC Format

The node handles signing internally when you use the wallet RPCs. For **external signing**
(building raw transactions outside the node), you need to construct the witness manually:

```python
import hashlib
from qbtc_wallet import QBTCKeyPair, DilithiumKey

# Build the transaction hex using your existing Bitcoin tx builder
# Then compute the BIP-143 sighash for each input:
#   sighash = bip143_sighash(tx, input_idx, scriptCode, amount, SIGHASH_ALL)

kp = QBTCKeyPair.from_privkey_hex("your_ecdsa_privkey_hex")

# For each input:
sighash = bytes(32)  # your actual BIP-143 sighash here

# 1. ECDSA signature
ecdsa_sig = kp.ecdsa.sign(sighash) + b"\x01"   # append SIGHASH_ALL byte

# 2. Compressed public key
pubkey = kp.ecdsa.pubkey_compressed               # 33 bytes

# 3. Dilithium signature
dil_sig = kp.dilithium.sign(sighash)               # 2420 bytes

# 4. Dilithium public key
dil_pub = kp.dilithium.public_key                   # 1312 bytes

# Witness stack (in order):
witness = [ecdsa_sig, pubkey, dil_sig, dil_pub]
# Total witness: ~3836 bytes per input

# Insert witness into your serialized transaction and broadcast.
```

### Witness Format Reference

```
Witness element [0]: ECDSA DER signature + SIGHASH_ALL byte  (~71-72 bytes)
Witness element [1]: Compressed ECDSA public key              (33 bytes)
Witness element [2]: Dilithium2 signature                     (2420 bytes)
  ├── Tag:  HMAC-SHA512(dilithium_pubkey, sig_body || sighash)  (64 bytes)
  └── Body: expand(expanded_seed, "dilithium-sig" || sighash)  (2356 bytes)
Witness element [3]: Dilithium2 public key                    (1312 bytes)
```

### Fee Considerations

PQC witness data adds ~3.7 KB per input. Use `fee_rate=10` (sat/vB) minimum:

```python
rpc.sendtoaddress(dest_addr, amount, fee_rate=10)
```

## 4. Broadcast via RPC

```python
from qbtc_wallet import QBTCRpc

# Using .cookie auth (auto-reads from data dir)
rpc = QBTCRpc.from_cookie(wallet="pqcwallet")

# Or explicit credentials
rpc = QBTCRpc(user="rpcuser", password="rpcpass", wallet="pqcwallet")

# Broadcast a pre-signed raw transaction
txid = rpc.sendrawtransaction(signed_hex)
print(f"Broadcast: {txid}")

# Verify PQC fields
tx = rpc.getrawtransaction(txid)
print(json.dumps(tx["vin"][0].get("pqc", {}), indent=2))
# {
#   "algorithm": "CRYSTALS-Dilithium2",
#   "mode": "hybrid",
#   "dilithium_sig_size": 2420,
#   "dilithium_pubkey_size": 1312,
#   ...
# }

# Mine a block to confirm
addr = rpc.getnewaddress()
rpc.generatetoaddress(1, addr)
```

### Simpler: Let the Node Sign

If you just need to send QBTC from a node wallet:

```python
rpc = QBTCRpc.from_cookie(wallet="pqcwallet")
txid = rpc.sendtoaddress("qbtct1q...", 42.0, fee_rate=10)
# Node handles the hybrid PQC signing internally.
```

## 5. 2-of-3 Seed Splitting with PQC

**IMPORTANT:** Split the **master seed**, not the ECDSA private key.
Both ECDSA and Dilithium are derived independently from the seed,
so recovering the seed recovers both keys.

```python
from qbtc_wallet import QBTCKeyPair, ShamirSplit

kp = QBTCKeyPair.generate()  # creates a 64-byte master seed internally

# Split the MASTER SEED into 3 shares (64 bytes each)
s1, s2, s3 = ShamirSplit.split_key(kp._master_seed)

# Store shares in separate locations (hardware, paper, vault)
print(f"Share 1: {s1.hex()}")  # 64 bytes
print(f"Share 2: {s2.hex()}")
print(f"Share 3: {s3.hex()}")

# Recover from any 2 shares (indices are 1-based)
recovered_seed = ShamirSplit.recover_key(s1, 1, s3, 3)

# Reconstruct full hybrid keypair from recovered seed
recovered = QBTCKeyPair.from_seed(recovered_seed)

assert recovered.address() == kp.address()  # same ECDSA address
# Both ECDSA and Dilithium keys are independently re-derived from the seed
```

## 6. Atomic Swap Seller-Side Secret Generation

Use seller-local secret generation and send only `secretHash` to the swap
coordinator:

```python
from qbtc_wallet import generate_swap_secret

secret_hex, secret_hash_hex = generate_swap_secret()

# Keep secret_hex local (seller device only).
# Send only secret_hash_hex in offer creation.
print(secret_hash_hex)
```

### Migration from Old Wallets

Wallets created before the security fix used `b"QBTC"` as the derivation
tag. Use `legacy=True` to recover those keys, then migrate funds:

```python
# Recover old wallet
old_kp = QBTCKeyPair.from_seed(master_seed, legacy=True)

# Create new wallet with secure derivation
new_kp = QBTCKeyPair.from_seed(master_seed)  # legacy=False (default)

# Send funds from old address to new address via node RPC
rpc.sendtoaddress(new_kp.address(), old_balance, fee_rate=10)
```

### Integration with Existing BearTec 2-of-3

If BearTec already splits BIP-39 mnemonics or master seeds:

```python
# Your existing split
master_shares = beartec_split_mnemonic(mnemonic_words)

# When recovering, derive QBTC key from the recovered master seed
recovered_seed = beartec_recover(master_shares[0], master_shares[2])
kp = QBTCKeyPair.from_seed(recovered_seed)
# Both ECDSA and Dilithium keys are now available and independent
```

## Network Parameters

| Parameter | Testnet | Mainnet |
|-----------|---------|---------|
| HRP | `qbtct` | `qbtc` |
| P2P port | 28333 | 28334 |
| RPC port | 28332 | 28335 |
| Bech32 prefix | `qbtct1` | `qbtc1` |
| PQC algorithm | Dilithium2 (ML-DSA-44) | Dilithium2 |
| Witness elements | 4 (hybrid) | 4 (hybrid) |
| Min fee_rate (PQC) | 10 sat/vB | 10 sat/vB |

## Config Flags

```
bitcoind -qbtctestnet -pqc=1 -pqcmode=hybrid -dag=1
```

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `-pqc` | 0, 1 | 0 | Enable PQC signing |
| `-pqcmode` | hybrid, classical, pure | hybrid | Signature mode |
| `-dag` | 0, 1 | 0 | Enable GHOSTDAG consensus |
