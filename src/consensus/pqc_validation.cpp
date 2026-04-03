#include <consensus/pqc_validation.h>
#include <consensus/pqc_witness.h>

namespace Consensus {

// PQC activation height.  Set to 0 so that PQC is active from genesis on all
// QBTC networks.  This matches the BIP9 deployment entry DEPLOYMENT_PQC which
// is set to ALWAYS_ACTIVE on QBTC chains.  On legacy Bitcoin chains
// DEPLOYMENT_PQC is set to NEVER_ACTIVE and this height check is moot.
static const int PQC_ACTIVATION_HEIGHT = 0;

bool IsPQCActivated(int nHeight)
{
    return nHeight >= PQC_ACTIVATION_HEIGHT;
}

bool HasPQCSignatures(const CTransaction& tx) {
    // Check for witness version 2 (PQC)
    for (const auto& input : tx.vin) {
        if (!input.scriptWitness.IsNull() && !input.scriptWitness.stack.empty()) {
            if (input.scriptWitness.stack[0].size() > 0 && input.scriptWitness.stack[0][0] == WITNESS_V2_PQC) {
                return true;
            }
        }
    }
    return false;
}

} // namespace Consensus
