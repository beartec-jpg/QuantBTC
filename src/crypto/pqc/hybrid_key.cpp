#include "hybrid_key.h"
#include "pqc_config.h"
#include <hash.h>
#include <key.h>
#include <util/system.h>

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
        // Generate PQC key pair
        PQCManager& manager = PQCManager::GetInstance();
        if (!manager.GenerateHybridKeys(m_pqc_public_key, m_pqc_private_key)) {
            return false;
        }
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

bool HybridKey::Sign(const uint256& hash, std::vector<unsigned char>& signature) const {
    if (!m_is_valid) {
        return false;
    }

    // Classical signature
    std::vector<unsigned char> classical_sig;
    if (!m_classical_key.Sign(hash, classical_sig)) {
        return false;
    }

    if (!PQCConfig::GetInstance().enable_hybrid_signatures) {
        signature = std::move(classical_sig);
        return true;
    }

    // PQC signature (placeholder - implement actual PQC signature)
    std::vector<unsigned char> pqc_sig;
    // TODO: Implement PQC signature generation
    
    // Combine signatures
    signature.clear();
    signature.insert(signature.end(), classical_sig.begin(), classical_sig.end());
    signature.insert(signature.end(), pqc_sig.begin(), pqc_sig.end());
    
    return true;
}

bool HybridKey::Verify(const uint256& hash, const std::vector<unsigned char>& signature) const {
    if (!m_is_valid) {
        return false;
    }

    if (!PQCConfig::GetInstance().enable_hybrid_signatures) {
        // Verify only classical signature
        return m_classical_key.Verify(hash, signature);
    }

    // Split signature into classical and PQC parts
    size_t classical_sig_size = 64; // Typical ECDSA signature size
    std::vector<unsigned char> classical_sig(signature.begin(), 
                                           signature.begin() + classical_sig_size);
    std::vector<unsigned char> pqc_sig(signature.begin() + classical_sig_size,
                                     signature.end());

    // Verify classical signature
    if (!m_classical_key.Verify(hash, classical_sig)) {
        return false;
    }

    // Verify PQC signature (placeholder - implement actual PQC verification)
    // TODO: Implement PQC signature verification
    
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
