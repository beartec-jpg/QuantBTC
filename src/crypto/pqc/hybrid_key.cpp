#include "hybrid_key.h"
#include "pqc_config.h"
#include "dilithium.h"
#include <hash.h>
#include <key.h>
#include <logging.h>

namespace pqc {

HybridKey::HybridKey() : m_is_valid(false) {}

HybridKey::~HybridKey() {
    if (!m_pqc_private_key.empty()) {
        memory_cleanse(m_pqc_private_key.data(), m_pqc_private_key.size());
    }
}

bool HybridKey::Generate() {
    // Generate classical key
    m_classical_key.MakeNewKey(true);

    if (PQCConfig::GetInstance().enable_pqc) {
        // Generate Dilithium signature keypair (not KEM)
        PQCManager& manager = PQCManager::GetInstance();
        std::vector<unsigned char> pqc_private_key_tmp;
        if (!manager.GenerateSignatureKeyPair(PQCAlgorithm::DILITHIUM,
                                              m_pqc_public_key, pqc_private_key_tmp)) {
            LogPrintf("HybridKey::Generate: Dilithium keygen failed; PQC is enabled, aborting\n");
            m_is_valid = false;
            return false;
        }
        m_pqc_private_key.assign(pqc_private_key_tmp.begin(), pqc_private_key_tmp.end());
        if (!pqc_private_key_tmp.empty()) {
            memory_cleanse(pqc_private_key_tmp.data(), pqc_private_key_tmp.size());
            pqc_private_key_tmp.clear();
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
    if (!m_pqc_private_key.empty()) {
        memory_cleanse(m_pqc_private_key.data(), m_pqc_private_key.size());
    }
    m_pqc_public_key = public_key;
    m_pqc_private_key.assign(private_key.begin(), private_key.end());
    m_is_valid = m_classical_key.IsValid();
    return true;
}

bool HybridKey::SignPQCMessage(const std::vector<unsigned char>& message,
                               std::vector<unsigned char>& signature) const {
    if (!m_is_valid || m_pqc_private_key.empty()) {
        return false;
    }

    // Use a short-lived copy only for the signing call, then cleanse it immediately.
    std::vector<unsigned char> privkey(m_pqc_private_key.begin(), m_pqc_private_key.end());
    PQCManager& manager = PQCManager::GetInstance();
    const bool ok = manager.Sign(PQCAlgorithm::DILITHIUM, message, privkey, signature);
    if (!privkey.empty()) {
        memory_cleanse(privkey.data(), privkey.size());
    }
    if (!ok) {
        LogPrintf("HybridKey::SignPQCMessage: Dilithium signing failed\n");
    }
    return ok;
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

    if (!PQCConfig::GetInstance().enable_hybrid_signatures) {
        signature = std::move(classical_sig);
        return true;
    }

    if (m_pqc_private_key.empty()) {
        LogPrintf("HybridKey::Sign: hybrid mode enabled but PQC private key is missing\n");
        return false;
    }

    // Real Dilithium PQC signature. This hybrid blob is for internal/P2P use and
    // is intentionally distinct from the on-chain 4-element witness path.
    std::vector<unsigned char> pqc_sig;
    std::vector<unsigned char> msg_bytes(hash.begin(), hash.end());
    if (!SignPQCMessage(msg_bytes, pqc_sig)) {
        LogPrintf("HybridKey::Sign: Dilithium signing failed in hybrid mode\n");
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

    // Cleanse intermediate signature material from non-locked heap pages.
    memory_cleanse(classical_sig.data(), classical_sig.size());
    memory_cleanse(pqc_sig.data(), pqc_sig.size());

    LogPrintf("HybridKey::Sign: hybrid signature produced (%u bytes: ECDSA=%u + Dilithium=%u)\n",
              signature.size(), csig_len, pqc_sig.size());
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

    // Detect hybrid format from the signature itself: [1-byte len][ECDSA][PQC].
    // If the signature is too short to contain a PQC component, treat as classical.
    // This avoids silently downgrading hybrid-signed txs when config changes.
    if (m_pqc_public_key.empty()) {
        return m_classical_key.GetPubKey().Verify(hash, signature);
    }
    {
        // Peek: if the leading length byte + ECDSA sig + at least Dilithium::SIGNATURE_SIZE
        // bytes are present, this is a hybrid signature — verify it as such regardless
        // of the current enable_hybrid_signatures config flag.
        bool looks_hybrid = false;
        if (signature.size() >= 2) {
            uint8_t csig_len_peek = signature[0];
            looks_hybrid = (signature.size() >= static_cast<size_t>(1 + csig_len_peek + Dilithium::SIGNATURE_SIZE));
        }
        if (!looks_hybrid) {
            return m_classical_key.GetPubKey().Verify(hash, signature);
        }
    }

    // Parse hybrid signature: [1 byte len] [classical_sig] [pqc_sig]
    if (signature.size() < 2) return false;
    
    uint8_t csig_len = signature[0];
    if (signature.size() < static_cast<size_t>(1 + csig_len + Dilithium::SIGNATURE_SIZE)) return false;
    
    std::vector<unsigned char> classical_sig(signature.begin() + 1, 
                                            signature.begin() + 1 + csig_len);
    std::vector<unsigned char> pqc_sig(signature.begin() + 1 + csig_len,
                                      signature.end());

    if (pqc_sig.size() != Dilithium::SIGNATURE_SIZE) return false;

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

    // Keep the secure member storage internal; use a short-lived copy only for the
    // KEM decapsulation call, then cleanse it immediately.
    std::vector<unsigned char> private_key(m_pqc_private_key.begin(), m_pqc_private_key.end());
    PQCManager& manager = PQCManager::GetInstance();
    const bool ok = manager.HybridDecapsulate(private_key, ciphertext, shared_secret);
    if (!private_key.empty()) {
        memory_cleanse(private_key.data(), private_key.size());
    }
    return ok;
}

} // namespace pqc
