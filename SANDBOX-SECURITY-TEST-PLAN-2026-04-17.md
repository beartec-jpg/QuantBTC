# QuantumBTC Sandbox Security Test Plan

Date: 2026-04-17
Scope: Post-fix security regression, consensus safety, wallet/witness integrity, DAG resilience, atomic swap HTLC hardening
Target repo: QuantBTC (QBlockQ/pqc-bitcoin fork)

## 1. Objectives

1. Verify recent security fixes remain effective under sandboxed execution.
2. Detect downgrade paths where ECDSA-only spends can bypass intended PQC protections.
3. Validate deterministic behavior across reorgs, restarts, and mixed-input transactions.
4. Validate EVM HTLC invariants (sha256 hashlock, CEI, non-reentrancy, timelock constraints).
5. Produce reproducible evidence for release readiness.

## 2. Sandbox Requirements

1. Isolated runtime per suite (fresh data dir and process namespace).
2. Deterministic seeds and fixed clocks where test harness supports it.
3. No shared wallet state across suites.
4. Artifact capture enabled:
- test logs
- node debug logs
- mempool acceptance/rejection traces
- serialized failing transactions
- performance counters (CPU, RAM)

## 3. Test Environment Matrix

1. Linux x86_64, release build, no GUI.
2. Regtest-like local mode for deterministic failure reproduction.
3. QBTC testnet mode for deployment-flag behavior validation.
4. Optional multi-node chaos lane (kill/restart and partial partition).

## 4. Build And Execution Pipeline

## 4.1 Build stage

Run from repo root:

- ./autogen.sh
- ./configure --with-incompatible-bdb --with-gui=no
- make -j$(nproc)

Build gate:
- bitcoind and bitcoin-cli binaries exist and start
- no compile/link errors

## 4.2 Security regression stage

Run high-priority suites first:

1. python3 test_pqc_security.py
2. python3 test_pqc_pubkey_unbinding.py
3. python3 test_sphincs_verify.py
4. python3 test_pqc_attacks.py

Gate:
- no unexpected failures
- all expected-negative checks are explicitly tagged in output

## 4.3 Stress and consensus stage

1. python3 test_parallel_dag.py
2. python3 test_parallel_dag2.py
3. python3 test_ghostdag_contention.py
4. python3 test_sustained_tps.py
5. ./run_hightp_test.sh

Gate:
- no consensus splits
- no unbounded memory growth trend during sustained load window

## 4.4 Recovery and adversarial stage

1. ./test_kill9_recovery.sh
2. ./test_restart_10k.sh
3. python3 test_dag_fork_v3.py
4. python3 test_dag_testnet.py

Gate:
- restart/recovery succeeds without chain corruption
- no stuck mempool or irrecoverable wallet state

## 5. Security-Focused Regression Matrix

1. Witness downgrade behavior
- Risk: ECDSA-only witness accepted where hybrid signatures are expected.
- Evidence focus: SCRIPT_VERIFY_HYBRID_SIG activation by chain/height, mempool reject reasons.
- Tests: test_pqc_security.py plus explicit two-element witness injection.

2. PQC pubkey substitution
- Risk: witness-supplied pqc pubkey mismatch accepted.
- Evidence focus: witness program hash mismatch behavior for hybrid addresses.
- Tests: test_pqc_pubkey_unbinding.py crafted attacker witness.

3. Mixed-input partial bypass
- Risk: one input hybrid, one input classical accepted in same tx.
- Evidence focus: per-input rejection path in pqc_validation.
- Tests: test_pqc_attacks.py mixed-input scenario.

4. Signature cache separation
- Risk: cross-domain cache collision or stale acceptance.
- Evidence focus: repeated verify behavior and cache key isolation.
- Tests: test_pqc_attacks.py cache checks.

5. DAG resource exhaustion
- Risk: pathological mergeset growth or CPU amplification.
- Evidence focus: mergeset bounds, tip-set behavior under parallel contention.
- Tests: contention and parallel DAG suites.

6. Atomic swap contract controls
- Risk: reentrancy, locktime griefing, hash mismatch semantics.
- Evidence focus: withdraw/refund CEI, ReentrancyGuard, MIN_LOCKTIME, sha256 usage.
- Tests: contract unit tests and scripted scenario replay in contrib/evm-htlc.

## 6. While-Building Workstream

If build is long-running, execute in parallel:

1. Static review of consensus flags by chain:
- DEPLOYMENT_PQC state
- nHybridSigHeight value
- effective script flags at current height

2. Test harness hardening:
- convert expected-failure security checks into explicit expected-negative assertions
- ensure output differentiates regression failure vs expected exploit-detection behavior

3. Artifact template prep:
- summary table (suite/pass/fail)
- risk mapping table (risk/test/result)
- sign-off checklist

## 7. Exit Criteria (Go/No-Go)

Go only if all are true:

1. Build succeeds and binaries are reproducible in sandbox.
2. Security suites show zero unexpected failures.
3. No high-severity downgrade path remains exploitable on target deployment chain.
4. Stress/recovery suites show no consensus integrity regression.
5. Audit evidence package is complete and reproducible.

No-Go if any of the following occurs:

1. ECDSA-only bypass accepted on a chain/profile that is intended to enforce hybrid.
2. Inconsistent mempool/consensus acceptance across equivalent nodes.
3. Reorg/restart leads to divergence or irreversible wallet inconsistency.

## 8. Immediate Run Order

1. Start build pipeline.
2. Run 4 PQC security suites.
3. Run DAG contention and sustained TPS lanes.
4. Run restart/recovery lanes.
5. Publish consolidated report with exploitability conclusions and remediation deltas.
