// Copyright (c) 2026 BearTec / QuantumBTC
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <crypto/pqc/pqc_config.h>
#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>
#include <tinyformat.h>

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

    for (size_t i = 0; i < tx.vin.size(); i++) {
        const auto& witness_stack = tx.vin[i].scriptWitness.stack;
        if (witness_stack.empty()) {
            continue;
        }

        if (witness_stack.size() == 4) {
            if (!IsPQCWitness(witness_stack[2], witness_stack[3])) {
                return state.Invalid(BlockValidationResult::BLOCK_CONSENSUS,
                                     "bad-pqc-witness",
                                     strprintf("Input %u: invalid PQC witness element sizes", i));
            }
        } else if ((flags & SCRIPT_VERIFY_HYBRID_SIG) && witness_stack.size() == 2) {
            // Every witness input must have PQC when HYBRID_SIG is enforced.
            return state.Invalid(BlockValidationResult::BLOCK_CONSENSUS,
                                 "missing-pqc-sig",
                                 strprintf("Input %u: missing required PQC signature (2-element witness)", i));
        } else if (witness_stack.size() != 2) {
            // Witness has >4 or ==3 elements — likely a P2WSH or P2TR script-path
            // spend.  The script interpreter in VerifyScript() fully validates
            // these, so we just skip the PQC-specific structural check here.
            continue;
        }
    }

    return true;
}

// NOTE: These functions are runtime configuration checks only.  They do NOT
// consult the BIP9 DEPLOYMENT_PQC soft-fork state.  The canonical consensus
// activation path is GetBlockScriptFlags() in validation.cpp, which calls
// DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_PQC).
bool IsPQCGloballyEnabled() {
    return pqc::PQCConfig::GetInstance().enable_pqc;
}
bool IsPQCGloballyRequired() {
    return IsPQCGloballyEnabled();
}

} // namespace Consensus
