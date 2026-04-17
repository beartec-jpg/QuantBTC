// Copyright (c) 2026 BearTec / QuantumBTC
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#ifndef BITCOIN_CONSENSUS_PQC_VALIDATION_H
#define BITCOIN_CONSENSUS_PQC_VALIDATION_H

#include <primitives/transaction.h>
#include <crypto/pqc/hybrid_key.h>
#include <script/interpreter.h>

class BlockValidationState;

namespace Consensus {

/** PQC validation flags */
static constexpr unsigned int SCRIPT_VERIFY_PQC = (1U << 21);
static constexpr unsigned int SCRIPT_VERIFY_HYBRID_SIG = (1U << 25);

/**
 * Check if a transaction includes PQC signatures.
 * Detects 4-element witness stacks with Dilithium or SPHINCS+ sized elements
 * matching the hybrid format produced by sign.cpp:
 *   [ECDSA sig, pubkey, PQC sig, PQC pubkey]
 * @param[in]   tx              The transaction to check
 * @return true if transaction contains PQC signatures
 */
bool HasPQCSignatures(const CTransaction& tx);

/**
 * Structural PQC witness precheck only.
 *
 * @param[in]   tx     The transaction to inspect
 * @param[in]   flags  Script verification flags
 * @param[out]  state  Validation state
 * @return true if PQC witness presence/element sizes are acceptable
 *
 * This function validates PQC witness presence and element sizes, but it does
 * NOT perform cryptographic signature verification. Real verification occurs in
 * `VerifyScript()` via `src/script/interpreter.cpp`, which has the required
 * scriptCode/sighash/amount context.
 */
bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, BlockValidationState& state);

/**
 * Check if PQC is globally enabled via the runtime configuration flag.
 *
 * NOTE: This is a runtime configuration check only.  It does NOT consult the
 * BIP9 DEPLOYMENT_PQC soft-fork state and is NOT height-sensitive.  For
 * consensus-level activation (the canonical source of truth), use
 * DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_PQC) in
 * validation.cpp / GetBlockScriptFlags().
 */
bool IsPQCGloballyEnabled();

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PQC_VALIDATION_H
