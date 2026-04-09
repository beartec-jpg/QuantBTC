// Copyright (c) 2026 BearTec / QuantumBTC
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <crypto/pqc/pqc_config.h>
#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>

namespace Consensus {

/** Return true if the 4-element witness has PQC-sized sig+pubkey elements. */
static bool IsPQCWitness(const std::vector<unsigned char>& sig_elem,
                         const std::vector<unsigned char>& pk_elem)
{
    // Dilithium (ML-DSA-44): sig=2420, pk=1312
    if (sig_elem.size() == pqc::Dilithium::SIGNATURE_SIZE &&
        pk_elem.size() == pqc::Dilithium::PUBLIC_KEY_SIZE)
        return true;
    // SPHINCS+ (SLH-DSA-SHA2-128f): sig==17088, pk=32
    if (sig_elem.size() == pqc::SPHINCS::SIGNATURE_SIZE &&
        pk_elem.size() == pqc::SPHINCS::PUBLIC_KEY_SIZE)
        return true;
    return false;
}

bool HasPQCSignatures(const CTransaction& tx) {
    for (const auto& input : tx.vin) {
        const auto& stack = input.scriptWitness.stack;
        if (stack.size() == 4 && IsPQCWitness(stack[2], stack[3])) {
            return true;
        }
    }
    return false;
}

bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, BlockValidationState& state) {
    // NOTE: This is intentionally a structural precheck only. Cryptographic PQC
    // verification is consensus-enforced in VerifyScript()/interpreter.cpp.
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
            if (IsPQCWitness(witness_stack[2], witness_stack[3])) {
                pqc_found = true;
            } else {
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
