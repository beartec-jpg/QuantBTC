#ifndef BITCOIN_CONSENSUS_PQC_VALIDATION_H
#define BITCOIN_CONSENSUS_PQC_VALIDATION_H

#include <consensus/validation.h>
#include <primitives/transaction.h>
#include <crypto/pqc/hybrid_key.h>

namespace Consensus {

/** PQC validation flags */
static const unsigned int SCRIPT_VERIFY_PQC = (1U << 24);  // Verify PQC signatures if present
static const unsigned int SCRIPT_VERIFY_HYBRID_SIG = (1U << 25);  // Require both classical and PQC signatures

/** 
 * Check if a transaction includes PQC signatures
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
bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, ValidationState& state);

/**
 * Check if block height requires PQC signatures
 * @param[in]   nHeight         Block height to check
 * @return true if PQC signatures are required at this height
 */
bool IsPQCRequired(int nHeight);

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PQC_VALIDATION_H
