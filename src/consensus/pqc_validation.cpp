#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <script/interpreter.h>
#include <crypto/pqc/pqc_config.h>
#include <consensus/pqc_witness.h>
#include <logging.h>

namespace Consensus {

// PQC activation height.  Set to 0 so that PQC is active from genesis on all
// QBTC networks.  This matches the BIP9 deployment entry DEPLOYMENT_PQC which
// is set to ALWAYS_ACTIVE on QBTC chains.  On legacy Bitcoin chains
// DEPLOYMENT_PQC is set to NEVER_ACTIVE and this height check is moot.
static const int PQC_ACTIVATION_HEIGHT = 0;

static bool IsPQCActivated(int nHeight)
{
    return nHeight >= PQC_ACTIVATION_HEIGHT;
}

// Forward declaration — defined below CheckPQCSignatures.
static bool VerifyPQCSignature(const CTransaction& tx, size_t nIn, const std::vector<unsigned char>& signature, const CScript& prevScript);

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

bool CheckPQCSignatures(const CTransaction& tx, unsigned int flags, TxValidationState& state) {
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
                
                // Verify PQC signature.
                // NOTE: Proper verification requires the previous output's scriptPubKey
                // which is not available here without UTXO access.  Pass an empty script;
                // full verification is performed by the script interpreter (VerifyScript).
                if (!VerifyPQCSignature(tx, i, pqc_sig, CScript())) {
                    return state.Invalid(TxValidationResult::TX_CONSENSUS,
                                       "bad-pqc-sig",
                                       "PQC signature verification failed");
                }
            }
        }
    }
    
    // If PQC signatures are required but none found
    if ((flags & SCRIPT_VERIFY_HYBRID_SIG) && !pqc_found) {
        return state.Invalid(TxValidationResult::TX_CONSENSUS,
                           "missing-pqc-sig",
                           "Missing required PQC signature");
    }
    
    return true;
}

bool IsPQCRequired(int nHeight) {
    // Check if we've reached activation threshold
    return IsPQCActivated(nHeight);
}

static bool VerifyPQCSignature(const CTransaction& tx, size_t nIn, const std::vector<unsigned char>& signature, const CScript& prevScript) {
    try {
        // Verify it's a PQC witness program
        int witnessversion;
        std::vector<unsigned char> program;
        if (!prevScript.IsWitnessProgram(witnessversion, program) || witnessversion != WITNESS_V2_PQC) {
            return false;
        }
        
        // Extract public key from witness program
        std::vector<unsigned char> pubKey(program.begin(), program.end());
        
        // Verify signature using PQC
        pqc::HybridKey key;
        if (!key.SetPQCPublicKey(pubKey)) {
            LogPrintf("VerifyPQCSignature: SetPQCPublicKey failed (pubkey size=%u, expected %u)\n",
                      pubKey.size(), pqc::Dilithium::PUBLIC_KEY_SIZE);
            return false;
        }
        
        // Compute the witness v0 sighash that covers this input.
        uint256 hash = SignatureHash(prevScript, tx, nIn, SIGHASH_ALL, 0, SigVersion::WITNESS_V0);
        
        return key.Verify(hash, signature);
    } catch (const std::exception&) {
        return false;
    }
}

} // namespace Consensus
