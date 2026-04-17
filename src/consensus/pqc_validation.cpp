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
            // Witness has a stack size that is neither 2 (ECDSA-only P2WPKH) nor
            // 4 (PQC hybrid).  Common examples that legitimately reach this branch:
            //
            //   3-element — P2WSH HTLC claim: [buyer_sig, secret, htlcScript]
            //                P2WSH HTLC refund: [seller_sig, 0x00, htlcScript]
            //   5-element — P2WSH multi-sig or other complex script-path spends
            //
            // For all of these the PQC structural precheck is not applicable; the
            // full script interpreter (VerifyScript / interpreter.cpp) already
            // validates them on their own terms, so we skip the PQC-specific check.
            //
            // *** MAINTENANCE NOTE ***
            // If a future PQC upgrade introduces a hybrid witness format whose
            // stack depth is *not* 2 or 4 (e.g. a 3-element PQC-Tapscript path),
            // that format MUST be handled with an explicit `if` branch ABOVE this
            // `else` block — DO NOT rely on this pass-through to validate it.
            // Failing to do so would silently skip PQC signature verification for
            // that input type.
            continue;
        }
    }

    return true;
}

// NOTE: This function is a runtime configuration check only.  It does NOT
// consult the BIP9 DEPLOYMENT_PQC soft-fork state.  The canonical consensus
// activation path is GetBlockScriptFlags() in validation.cpp, which calls
// DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_PQC).
bool IsPQCGloballyEnabled() {
    return pqc::PQCConfig::GetInstance().enable_pqc;
}

} // namespace Consensus
