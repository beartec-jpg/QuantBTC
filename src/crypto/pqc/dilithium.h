#ifndef BITCOIN_CRYPTO_PQC_DILITHIUM_H
#define BITCOIN_CRYPTO_PQC_DILITHIUM_H

#include <stdint.h>
#include <vector>

#include <oqs/oqs.h>

namespace pqc {

/**
 * CRYSTALS-Dilithium / ML-DSA-44 digital signature scheme.
 *
 * Wraps the liboqs OQS_SIG implementation of NIST FIPS 204 (ML-DSA-44),
 * the mandatory post-quantum digital signature standard.
 *
 * Security level: NIST Level 2 (roughly equivalent to AES-128).
 */
class Dilithium {
public:
    // ML-DSA-44 sizes from FIPS 204 / liboqs
    static constexpr size_t PUBLIC_KEY_SIZE = OQS_SIG_ml_dsa_44_length_public_key;   // 1312
    static constexpr size_t PRIVATE_KEY_SIZE = OQS_SIG_ml_dsa_44_length_secret_key;  // 2560
    static constexpr size_t SIGNATURE_SIZE = OQS_SIG_ml_dsa_44_length_signature;     // 2420

    Dilithium();
    ~Dilithium();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool DeriveKeyPair(const std::vector<uint8_t>& seed, std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_DILITHIUM_H
