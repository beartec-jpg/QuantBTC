#!/usr/bin/env python3
"""
getpqcinfo RPC Test
===================
Verifies that the getpqcinfo RPC returns correct Falcon-512 parameters.
"""

import subprocess, json, os, shutil, time, sys

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
DATADIR  = os.path.join(os.environ.get("TMPDIR", "/tmp"), "getpqcinfo_regtest")
RPC_PORT = "18752"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))
    return ok

def cli(*args):
    base = [CLI, f"-datadir={DATADIR}", "-regtest", f"-rpcport={RPC_PORT}",
            "-rpcuser=test", "-rpcpassword=test"]
    out = subprocess.run(base + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"CLI error ({args[0]}): {out.stderr.strip()}")
    return out.stdout.strip()

def cli_json(*args):
    return json.loads(cli(*args))

def start_node():
    if os.path.exists(DATADIR):
        shutil.rmtree(DATADIR)
    os.makedirs(f"{DATADIR}/regtest", exist_ok=True)
    cmd = [BITCOIND, f"-datadir={DATADIR}", "-regtest",
           f"-rpcport={RPC_PORT}", "-rpcuser=test", "-rpcpassword=test",
           "-pqc=1", "-pqcsig=falcon", "-nodebug"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.5)
        try:
            cli("getblockchaininfo")
            return proc
        except Exception:
            pass
    raise RuntimeError("Node failed to start")

def stop_node(proc):
    try:
        cli("stop")
        proc.wait(timeout=15)
    except Exception:
        proc.terminate()
        proc.wait()
    shutil.rmtree(DATADIR, ignore_errors=True)

def run_test():
    proc = None
    try:
        print("\n=== getpqcinfo RPC Test ===\n")
        proc = start_node()
        info = cli_json("getpqcinfo")

        report("scheme is 'falcon'", info.get("scheme") == "falcon", info.get("scheme"))
        report("standard references FIPS 206 / FN-DSA", "FIPS 206" in info.get("standard", ""),
               info.get("standard"))
        report("pubkey_size == 897", info.get("pubkey_size") == 897,
               str(info.get("pubkey_size")))
        report("sig_size == 666", info.get("sig_size") == 666,
               str(info.get("sig_size")))
        report("privkey_size == 1281", info.get("privkey_size") == 1281,
               str(info.get("privkey_size")))
        report("seed_size == 48", info.get("seed_size") == 48,
               str(info.get("seed_size")))
        report("security_bits_quantum == 128", info.get("security_bits_quantum") == 128,
               str(info.get("security_bits_quantum")))
        report("security_bits_classical == 256", info.get("security_bits_classical") == 256,
               str(info.get("security_bits_classical")))
        report("nist_level == '1'", info.get("nist_level") == "1",
               info.get("nist_level"))
        report("constant_time is True", info.get("constant_time") is True,
               str(info.get("constant_time")))
        report("implementation mentions PQClean",
               "PQClean" in info.get("implementation", ""),
               info.get("implementation"))
        report("constant_time_note mentions hash_to_point_ct",
               "hash_to_point_ct" in info.get("constant_time_note", ""),
               info.get("constant_time_note", "")[:60] + "...")

    except Exception as e:
        import traceback
        print(f"\n  [ERROR] {e}")
        traceback.print_exc()
        results.append(("Test completed without exception", False))
    finally:
        if proc:
            stop_node(proc)

    print("\n" + "="*45)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"Results: {passed}/{total} passed")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print()
    return passed == total

if __name__ == "__main__":
    sys.exit(0 if run_test() else 1)
