# QuantumBTC To-Do List

## 🔴 Critical — Security / Functional Breakage

- [ ] **Replace fake Dilithium with real ML-DSA** — `src/crypto/pqc/dilithium.cpp` is an HMAC-SHA512 MAC, not lattice cryptography. Integrate the NIST ML-DSA reference implementation or liboqs.
- [ ] **Implement SPHINCS+, Falcon, SQIsign** — all three `Verify()` methods return `true` unconditionally, accepting any forged signature (`sphincs.cpp:51`, `falcon.cpp:51`, `sqisign.cpp:51`).
- [ ] **Fix Kyber KEM** — fix the NTT zeta table (120 elements, needs 128), fix `Encaps` to regenerate matrix `a` from seed instead of reading uninitialized `pk` memory at offset 544 (`kyber.cpp:130,137`), implement `InverseNTT`.
- [ ] **Fix NTRU KEM** — initialize `out[]` and `aux[]` in `poly_invert`, replace the broken extended-GCD loop with a correct implementation (`ntru.cpp:35–77`).
- [ ] **Fix FrodoKEM stack overflow** — move `uint16_t A[976*976]` (~1.82 MB) to heap in `KeyGen` and `Encaps` (`frodokem.cpp:42,107`).
- [ ] **Implement real Dilithium verification in the script interpreter** — `interpreter.cpp:1898–1913` currently strips the Dilithium witness elements with a size check only; actual cryptographic verification must be called there.
- [ ] **Fix regtest magic bytes and port collision** — `chainparams.cpp:683–687` uses `0xfa 0xbf 0xb5 0xda` / port `18444`, identical to Bitcoin Core regtest. Choose unique values.
- [ ] **Add IND-CCA2 (Fujisaki-Okamoto) transform to all three KEMs** — Kyber, NTRU, FrodoKEM `Decaps` must re-encrypt and compare to reject invalid ciphertexts; without this they are vulnerable to adaptive attacks.

## 🟠 High — Build Failures / Major Bugs

- [ ] **Fix `pqc_validation.cpp` compilation errors** — calls `IsPQCActivated` (undefined), `HybridKey::SetPQCPublicKey` (doesn't exist), uses removed `ValidationInvalidReason::CONSENSUS` and `REJECT_INVALID` API, and accesses `tx.vin[nIn].prevout.scriptPubKey` which doesn't exist on `COutPoint`. Either implement all missing functions or rewrite using the current Bitcoin Core v28 API.
- [ ] **Define `IsPQCActivated`** — called by `pqc_validation.cpp:68` but defined nowhere.
- [ ] **Fix duplicate `SCRIPT_VERIFY_PQC` flag** — `pqcscript.h` defines it as `(1U << 31)`, `pqc_validation.h` as `(1U << 24)`; pick one.
- [ ] **Fix Kyber/NTRU/FrodoKEM size constant mismatches** — `KYBER_PUBLIC_KEY_BYTES=1184` but implementation writes 544 bytes; `NTRU_PUBLIC_KEY_BYTES=1230` but writes 1642 bytes; `FRODO_PUBLIC_KEY_BYTES=15632` but writes 15648 bytes; `FRODO_SHARED_SECRET_BYTES=24` but implementation produces 32 bytes (buffer overflow on callers).
- [ ] **Fix `-pqcsig=` argument parsing off-by-one** — `pqc_config.cpp:55` uses `substr(0,9)` for an 8-character prefix; change to `substr(0,8)` and `substr(8)`.
- [ ] **Fix `DagTipSet::BlockDisconnected` score corruption** — re-added parent tips get `blue_score=0` (`dagtipset.cpp:53`); look up and restore the correct blue score from the block index.

## 🟡 Medium — Correctness / Consensus Safety

- [ ] **Add duplicate-parent detection across `hashParents` elements** — `validation.cpp:4345` only checks for duplicates against `hashPrevBlock`, not among the extra parents themselves. A block with `hashParents=[A,A,B]` passes validation.
- [ ] **Fix GHOSTDAG inherited blues approximation** — `ghostdag.cpp:193–208` uses only `K+1` chain ancestors as the inherited blue set instead of the full blue set of the selected parent, causing incorrect blue/red classifications that can diverge between nodes.
- [ ] **Add a real depth limit to `IsBlockAncestor` BFS** — the comment says "depth limit" but none exists (`ghostdag_blockindex.h:97–110`); add a hard cap to prevent `O(DAG²)` cost per block acceptance.
- [ ] **Enforce `nMaxBlockWeightPQC`** — the parameter is set in chain params but never checked in validation or policy code.
- [ ] **Assert QBTC genesis block hashes** — `chainparams.cpp:612,719` compute but do not assert the genesis hash; add `assert(consensus.hashGenesisBlock == uint256{...})` with pre-computed values.
- [ ] **Fix `fPowNoRetargeting=true` on QBTC testnet** — this makes `nDagTargetSpacingMs=2000` a no-op since the DAA immediately returns the current bits (`pow.cpp:32`). Either remove `fPowNoRetargeting` or document that retargeting is intentionally disabled.
- [ ] **Make `HybridKey::Sign` fallback behavior explicit** — when Dilithium fails, it silently produces a raw ECDSA sig (no 1-byte prefix), which will fail verification if `enable_hybrid_signatures=true`. Either always use the hybrid format or return an error on failure.

## 🟢 Low — Code Quality / Minor Issues

- [ ] **Fix `GetMiningParents` iteration order documentation** — `dagtipset.h` says "highest-scored tips first"; confirm the `TipOrder` comparator and iteration direction are consistent.
- [ ] **Fix locally-mined blocks bypass activation delay** — `validation.cpp:4608` applies only IP throttle + ramp weight for `peer_id=-1`; the peer activation delay is also not applied to local miners, making the protection bypassable.
- [ ] **Replace `std::mt19937` with Bitcoin Core RNG in `earlyprotection.h:324`** — `std::random_device` may be deterministic on some platforms; use `GetRandInt()`.
- [x] **Fix `qbtc-mine.sh` mining descriptor** — replaced `raw(51)#8lvh9jxk` anyone-can-spend descriptors with proper P2WPKH addresses via `getnewaddress`.
- [ ] **Fix `QBTCRpc.sendtoaddress` in wallet** — `qbtc_wallet.py:443` passes a dict as `params`, but the RPC method expects positional args.
- [ ] **Fix `pqc_config.cpp` PQC algorithm config** — `pqc_config.h` defaults `enabled_kems` to Kyber+FrodoKEM+NTRU and `enabled_signatures` to Dilithium+Falcon, but both are broken; default to empty/disabled until fixed.
- [ ] **Add `hashParents` ancestral ordering check** — optionally verify that DAG parents don't include the block's own selected-chain descendants (prevents trivial DAG cycles).
- [ ] **Add regtest assumeutxo data for QBTC** — current regtest `m_assumeutxo_data` (`chainparams.cpp:737–758`) contains hardcoded Bitcoin Core regtest hashes that will be wrong.
- [ ] **Add unit tests for DAG** — no unit tests exist in `src/test/` for GHOSTDAG, `DagTipSet`, or DAG parent validation; the test files in the repo root are integration scripts requiring a running node.
- [ ] **`ComputeVirtualSelectedParentChain` calls `SelectBestParent` twice** (`ghostdag.cpp:306–308`) — minor inefficiency, store the result.
- [ ] **Document that Dilithium/KEM keys are test-only** — add clear `// NOT PRODUCTION` warnings to all PQC files and the wallet until real algorithm implementations land.