#ifndef BITCOIN_CRYPTO_PQC_HYBRID_KEY_H
#define BITCOIN_CRYPTO_PQC_HYBRID_KEY_H

#include <key.h>
#include <support/allocators/secure.h>
#include "pqc_manager.h"
#include <vector>
#include <memory>

namespace pqc {

class HybridKey {
public:
    using PQCPrivateKey = std::vector<unsigned char, secure_allocator<unsigned char>>;

    HybridKey();
    ~HybridKey();

    // Generate new hybrid key pair
    bool Generate();

    // Import existing keys
    bool SetClassicalKey(const CKey& key);
    bool SetPQCKey(const std::vector<unsigned char>& public_key,
                   const std::vector<unsigned char>& private_key);
    // Set only the PQC public key (verification-only mode; no classical key required).
    bool SetPQCPublicKey(const std::vector<unsigned char>& public_key);

    // Key operations
    // Produces an internal hybrid blob format: [1-byte ECDSA len][ECDSA sig][PQC sig].
    // This is NOT the on-chain 4-element witness format used by consensus spending.
    bool Sign(const uint256& hash, std::vector<unsigned char>& signature) const;
    bool Verify(const uint256& hash, const std::vector<unsigned char>& signature) const;

    // Produce a detached PQC signature over the supplied message without exposing
    // the raw private key material to external callers.
    bool SignPQCMessage(const std::vector<unsigned char>& message,
                        std::vector<unsigned char>& signature) const;
    
    // Key encapsulation
    bool Encapsulate(std::vector<unsigned char>& ciphertext,
                     std::vector<unsigned char>& shared_secret) const;
    bool Decapsulate(const std::vector<unsigned char>& ciphertext,
                     std::vector<unsigned char>& shared_secret) const;

    // Getters
    bool IsValid() const { return m_is_valid; }
    bool IsCompressed() const { return m_classical_key.IsCompressed(); }
    const CKey& GetClassicalKey() const { return m_classical_key; }
    const std::vector<unsigned char>& GetPQCPublicKey() const { return m_pqc_public_key; }
    bool HasPQCPrivateKey() const { return !m_pqc_private_key.empty(); }

private:
    bool m_is_valid;
    CKey m_classical_key;
    std::vector<unsigned char> m_pqc_public_key;
    PQCPrivateKey m_pqc_private_key;
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_HYBRID_KEY_H
