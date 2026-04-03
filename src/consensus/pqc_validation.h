#ifndef BITCOIN_CONSENSUS_PQC_VALIDATION_H
#define BITCOIN_CONSENSUS_PQC_VALIDATION_H

#include <primitives/transaction.h>

namespace Consensus {

/**
 * Check if PQC is activated at the given block height.
 * PQC is active from genesis (height 0) on all QBTC networks.  On legacy
 * Bitcoin chains DEPLOYMENT_PQC is NEVER_ACTIVE and this check is moot.
 * @param[in]   nHeight         Block height to check
 * @return true if PQC is activated at this height
 */
bool IsPQCActivated(int nHeight);

/**
 * Check if a transaction includes PQC signatures.
 * Looks for witness version 2 (WITNESS_V2_PQC) in the witness stacks.
 * @param[in]   tx              The transaction to check
 * @return true if transaction contains PQC signatures
 */
bool HasPQCSignatures(const CTransaction& tx);

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PQC_VALIDATION_H
