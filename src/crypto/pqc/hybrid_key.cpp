#include "hybrid_key.h"
#include "pqc_config.h"
#include "dilithium.h"
#include <hash.h>
#include <key.h>
#include <logging.h>

namespace pqc {

HybridKey::HybridKey() : m_is_valid(false) {}

HybridKey::~HybridKey() {
    // Secure cleanup
    memory_cleanse(m_pqc_private_key.data(), m_pqc_private_key.size());
}

bool HybridKey::Generate() {
    // Generate classical key
    m_classical_key.MakeNewKey(true);
    
    if (PQCConfig::GetInstance().enable_pqc) {
        // Generate Dilithium signature keypair (not KEM)
        PQCManager& manager = PQCManager::GetInstance();
        if (!manager.GenerateSignatureKeyPair(PQCAlgorithm::DILITHIUM,
                                              m_pqc_public_key, m_pqc_private_key)) {
            LogPrintf("HybridKey::Generate: Dilithium keygen failed, falling back to classical-only\n");
            // Still valid as a classical key
            m_is_valid = true;
            return true;
        }
        LogPrintf("HybridKey::Generate: generated hybrid key (ECDSA + Dilithium, pqc_pk=%u bytes)\n",
                  m_pqc_public_key.size());
    }
    
    m_is_valid = true;
    return true;
}

bool HybridKey::SetClassicalKey(const CKey& key) {
    if (!key.IsValid()) {
        return false;
    }
    m_classical_key = key;
    m_is_valid = !m_pqc_public_key.empty() || !PQCConfig::GetInstance().enable_pqc;
    return true;
}

bool HybridKey::SetPQCKey(const std::vector<unsigned char>& public_key,
                         const std::vector<unsigned char>& private_key) {
    if (public_key.empty() || private_key.empty()) {
        return false;
    }
    m_pqc_public_key = public_key;
    m_pqc_private_key = private_key;
    m_is_valid = m_classical_key.IsValid();
    return true;
}

bool HybridKey::SetPQCPublicKey(const std::vector<unsigned char>& public_key) {
    if (public_key.size() != Dilithium::PUBLIC_KEY_SIZE) {
        return false;
    }
    m_pqc_public_key = public_key;
    // Mark valid for verification-only use even without a classical key.
    m_is_valid = true;
    return true;
}

bool HybridKey::Sign(const uint256& hash, std::vector<unsigned char>& signature) const {
    if (!m_is_valid) {
        return false;
    }

    // Classical ECDSA signature
    std::vector<unsigned char> classical_sig;
    if (!m_classical_key.Sign(hash, classical_sig)) {
        return false;
    }

    if (!PQCConfig::GetInstance().enable_hybrid_signatures || m_pqc_private_key.empty()) {
        signature = std::move(classical_sig);
        return true;
    }

    // Real Dilithium PQC signature
    std::vector<unsigned char> pqc_sig;
    std::vector<unsigned char> msg_bytes(hash.begin(), hash.end());
    PQCManager& manager = PQCManager::GetInstance();
    if (!manager.Sign(PQCAlgorithm::DILITHIUM, msg_bytes, m_pqc_private_key, pqc_sig)) {
        LogPrintf("HybridKey::Sign: Dilithium signing failed; hybrid mode requires PQC signature\n");
        return false;
    }

    // Hybrid signature format:
    //   [1 byte: classical_sig_len] [classical_sig] [pqc_sig]
    // This allows the verifier to split without hardcoded offsets.
    signature.clear();
    uint8_t csig_len = static_cast<uint8_t>(classical_sig.size());
    signature.push_back(csig_len);
    signature.insert(signature.end(), classical_sig.begin(), classical_sig.end());
    signature.insert(signature.end(), pqc_sig.begin(), pqc_sig.end());
    
    LogPrintf("HybridKey::Sign: hybrid signature produced (%u bytes: ECDSA=%u + Dilithium=%u)\n",
              signature.size(), classical_sig.size(), pqc_sig.size());
    return true;
}

bool HybridKey::Verify(const uint256& hash, const std::vector<unsigned char>& signature) const {
    if (!m_is_valid) {
        return false;
    }

    // PQC-only verification mode: classical key was never set (e.g. via SetPQCPublicKey).
    if (!m_classical_key.IsValid() && !m_pqc_public_key.empty()) {
        std::vector<unsigned char> msg_bytes(hash.begin(), hash.end());
        PQCManager& manager = PQCManager::GetInstance();
        return manager.Verify(PQCAlgorithm::DILITHIUM, msg_bytes, signature, m_pqc_public_key);
    }

    if (!PQCConfig::GetInstance().enable_hybrid_signatures || m_pqc_public_key.empty()) {
        // Verify only classical signature
        return m_classical_key.GetPubKey().Verify(hash, signature);
    }

    // Parse hybrid signature: [1 byte len] [classical_sig] [pqc_sig]
    if (signature.size() < 2) return false;
    
    uint8_t csig_len = signature[0];
    if (signature.size() < static_cast<size_t>(1 + csig_len + 1)) return false;
    
    std::vector<unsigned char> classical_sig(signature.begin() + 1, 
                                            signature.begin() + 1 + csig_len);
    std::vector<unsigned char> pqc_sig(signature.begin() + 1 + csig_len,
                                      signature.end());

    // Verify classical ECDSA signature
    if (!m_classical_key.GetPubKey().Verify(hash, classical_sig)) {
        LogPrintf("HybridKey::Verify: ECDSA verification failed\n");
        return false;
    }

    // Verify Dilithium PQC signature
    std::vector<unsigned char> msg_bytes(hash.begin(), hash.end());
    PQCManager& manager = PQCManager::GetInstance();
    if (!manager.Verify(PQCAlgorithm::DILITHIUM, msg_bytes, pqc_sig, m_pqc_public_key)) {
        LogPrintf("HybridKey::Verify: Dilithium verification failed\n");
        return false;
    }

    return true;
}

bool HybridKey::Encapsulate(std::vector<unsigned char>& ciphertext,
                           std::vector<unsigned char>& shared_secret) const {
    if (!m_is_valid || m_pqc_public_key.empty()) {
        return false;
    }

    PQCManager& manager = PQCManager::GetInstance();
    return manager.HybridEncapsulate(m_pqc_public_key, ciphertext, shared_secret);
}

bool HybridKey::Decapsulate(const std::vector<unsigned char>& ciphertext,
                           std::vector<unsigned char>& shared_secret) const {
    if (!m_is_valid || m_pqc_private_key.empty()) {
        return false;
    }

    PQCManager& manager = PQCManager::GetInstance();
    return manager.HybridDecapsulate(m_pqc_private_key, ciphertext, shared_secret);
}

} // namespace pqc
