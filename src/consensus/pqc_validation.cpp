#include <consensus/pqc_validation.h>
#include <consensus/validation.h>
#include <script/interpreter.h>
#include <crypto/pqc/pqc_config.h>

namespace Consensus {

bool HasPQCSignatures(const CTransaction& tx) {
    // Check each input for PQC signatures
    for (const auto& input : tx.vin) {
        // PQC signatures are appended after classical signatures
        // Format: [classical_sig_length][classical_sig][pqc_sig_length][pqc_sig]
        const std::vector<unsigned char>& script_sig = input.scriptSig;
        
        // Basic size check
        if (script_sig.size() < 2) {
            continue;
        }
        
        // Parse signature format
        size_t classical_sig_len = script_sig[0];
        if (script_sig.size() > classical_sig_len + 2) {
            size_t pqc_sig_offset = classical_sig_len + 1;
            size_t pqc_sig_len = script_sig[pqc_sig_offset];
            
            // Check if PQC signature is present
            if (script_sig.size() >= pqc_sig_offset + 1 + pqc_sig_len) {
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
        const std::vector<unsigned char>& script_sig = input.scriptSig;
        
        // Parse signature format
        if (script_sig.size() < 2) {
            continue;
        }
        
        size_t classical_sig_len = script_sig[0];
        if (script_sig.size() <= classical_sig_len + 1) {
            continue;
        }
        
        size_t pqc_sig_offset = classical_sig_len + 1;
        size_t pqc_sig_len = script_sig[pqc_sig_offset];
        
        // Check if PQC signature is present
        if (script_sig.size() >= pqc_sig_offset + 1 + pqc_sig_len) {
            pqc_found = true;
            
            // Extract PQC signature
            std::vector<unsigned char> pqc_sig(
                script_sig.begin() + pqc_sig_offset + 1,
                script_sig.begin() + pqc_sig_offset + 1 + pqc_sig_len
            );
            
            // Verify PQC signature
            // Note: This requires access to the corresponding public key
            // which should be available in the previous output's script
            if (!VerifyPQCSignature(tx, i, pqc_sig)) {
                return state.Invalid(ValidationInvalidReason::CONSENSUS,
                                   false,
                                   REJECT_INVALID, "bad-pqc-sig",
                                   "PQC signature verification failed");
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
    // Define activation height for PQC requirement
    // This should be coordinated with the network upgrade
    static const int PQC_ACTIVATION_HEIGHT = 800000; // Example height
    
    return nHeight >= PQC_ACTIVATION_HEIGHT;
}

static bool VerifyPQCSignature(const CTransaction& tx, size_t nIn, const std::vector<unsigned char>& signature) {
    // Get the corresponding public key from the previous output
    // This is a placeholder - actual implementation needs to:
    // 1. Get the previous output
    // 2. Extract the public key
    // 3. Verify using appropriate PQC algorithm
    
    try {
        // Get previous output script
        const CTxOut& prevout = tx.vin[nIn].prevout;
        CScript prevScript = prevout.scriptPubKey;
        
        // Extract public key
        std::vector<unsigned char> pubKey;
        // ... extract public key from prevScript ...
        
        // Verify signature using PQC
        pqc::HybridKey key;
        if (!key.SetPQCPublicKey(pubKey)) {
            return false;
        }
        
        // Create transaction hash for signing
        uint256 hash = SignatureHash(prevScript, tx, nIn, SIGHASH_ALL, 0);
        
        return key.Verify(hash, signature);
    } catch (const std::exception&) {
        return false;
    }
}

} // namespace Consensus
