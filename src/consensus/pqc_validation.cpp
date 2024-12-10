#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <script/interpreter.h>
#include <crypto/pqc/pqc_config.h>
#include <consensus/pqc_witness.h>

namespace Consensus {

bool HasPQCSignatures(const CTransaction& tx) {
    // Check for witness version 2 (PQC)
    for (const auto& input : tx.vin) {
        if (!input.witness.IsNull() && !input.witness.stack.empty()) {
            if (input.witness.stack[0].size() > 0 && input.witness.stack[0][0] == WITNESS_V2_PQC) {
                return true;
            }
        }
    }
    return false;
}

bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, ValidationState& state) {
    if (!(flags & SCRIPT_VERIFY_PQC)) {
        // PQC verification not required
        return true;
    }

    bool pqc_found = false;
    
    // Check each input
    for (size_t i = 0; i < tx.vin.size(); i++) {
        const auto& input = tx.vin[i];
        
        // Check for PQC witness data
        if (!input.witness.IsNull() && !input.witness.stack.empty()) {
            const auto& witness_stack = input.witness.stack;
            
            // Check if this is a PQC witness program
            if (witness_stack[0].size() > 0 && witness_stack[0][0] == WITNESS_V2_PQC) {
                pqc_found = true;
                
                // Extract PQC signature from witness
                std::vector<unsigned char> pqc_sig = witness_stack[1];
                
                // Verify PQC signature
                if (!VerifyPQCSignature(tx, i, pqc_sig)) {
                    return state.Invalid(ValidationInvalidReason::CONSENSUS,
                                       false,
                                       REJECT_INVALID, "bad-pqc-sig",
                                       "PQC signature verification failed");
                }
            }
        }
    }
    
    // If PQC signatures are required but none found
    if ((flags & SCRIPT_VERIFY_HYBRID_SIG) && !pqc_found) {
        return state.Invalid(ValidationInvalidReason::CONSENSUS,
                           false,
                           REJECT_INVALID, "missing-pqc-sig",
                           "Missing required PQC signature");
    }
    
    return true;
}

bool IsPQCRequired(int nHeight) {
    // Check if we've reached activation threshold
    return IsPQCActivated(nHeight);
}

static bool VerifyPQCSignature(const CTransaction& tx, size_t nIn, const std::vector<unsigned char>& signature) {
    try {
        // Get previous output script
        const CTxOut& prevout = tx.vin[nIn].prevout;
        CScript prevScript = prevout.scriptPubKey;
        
        // Verify it's a PQC witness program
        std::vector<unsigned char> program;
        if (!prevScript.IsWitnessProgram(program) || program[0] != WITNESS_V2_PQC) {
            return false;
        }
        
        // Extract public key from witness program
        std::vector<unsigned char> pubKey(program.begin() + 1, program.end());
        
        // Verify signature using PQC
        pqc::HybridKey key;
        if (!key.SetPQCPublicKey(pubKey)) {
            return false;
        }
        
        // Create transaction hash for signing (using witness v2 sighash)
        uint256 hash = SignatureHashWitness(prevScript, tx, nIn, SIGHASH_ALL, 0);
        
        return key.Verify(hash, signature);
    } catch (const std::exception&) {
        return false;
    }
}

} // namespace Consensus
