#ifndef BITCOIN_CONSENSUS_PQC_VALIDATION_H
#define BITCOIN_CONSENSUS_PQC_VALIDATION_H

#include <primitives/transaction.h>
#include <crypto/pqc/hybrid_key.h>
#include <script/pqcscript.h>

namespace Consensus {

/** PQC validation flags */
static constexpr unsigned int SCRIPT_VERIFY_PQC = ::SCRIPT_VERIFY_PQC;  // Keep in sync with script flag definition.
static const unsigned int SCRIPT_VERIFY_HYBRID_SIG = (1U << 25);  // Require both classical and PQC signatures

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
 * Validate PQC signatures in a transaction
 * @param[in]   tx              The transaction to validate
 * @param[in]   flags          Script verification flags
 * @param[out]  state          Validation state
 * @return true if all PQC signatures are valid
 */
bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, BlockValidationState& state);

/**
 * Check if PQC is activated for a given height.
 */
bool IsPQCActivated(int nHeight);

/**
 * Check if block height requires PQC signatures
 * @param[in]   nHeight         Block height to check
 * @return true if PQC signatures are required at this height
 */
bool IsPQCRequired(int nHeight);

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PQC_VALIDATION_H
