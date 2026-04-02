#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <crypto/pqc/pqc_config.h>
#include <crypto/pqc/dilithium.h>

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
    for (const auto& input : tx.vin) {
        const auto& stack = input.scriptWitness.stack;
        if (stack.size() == 4 &&
            stack[2].size() == pqc::Dilithium::SIGNATURE_SIZE &&
            stack[3].size() == pqc::Dilithium::PUBLIC_KEY_SIZE) {
                return true;
        }
    }
    return false;
}

bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, BlockValidationState& state) {
    if (!(flags & SCRIPT_VERIFY_PQC)) {
        return true;
    }

    bool pqc_found = false;

    for (size_t i = 0; i < tx.vin.size(); i++) {
        const auto& witness_stack = tx.vin[i].scriptWitness.stack;
        if (witness_stack.empty()) {
            continue;
        }

        if (witness_stack.size() == 4) {
            pqc_found = true;
            if (witness_stack[2].size() != pqc::Dilithium::SIGNATURE_SIZE ||
                witness_stack[3].size() != pqc::Dilithium::PUBLIC_KEY_SIZE) {
                return state.Invalid(BlockValidationResult::BLOCK_CONSENSUS,
                                     "bad-pqc-witness",
                                     "Invalid PQC witness element sizes");
            }
        }
    }

    if ((flags & SCRIPT_VERIFY_HYBRID_SIG) && !pqc_found) {
        return state.Invalid(BlockValidationResult::BLOCK_CONSENSUS,
                             "missing-pqc-sig",
                             "Missing required PQC signature");
    }

    return true;
}

bool IsPQCActivated(int nHeight) {
    (void)nHeight;
    return pqc::PQCConfig::GetInstance().enable_pqc;
}

bool IsPQCRequired(int nHeight) {
    return IsPQCActivated(nHeight);
}

} // namespace Consensus
