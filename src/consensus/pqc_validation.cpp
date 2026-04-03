#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <crypto/pqc/pqc_config.h>
#include <crypto/pqc/dilithium.h>

namespace Consensus {

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
