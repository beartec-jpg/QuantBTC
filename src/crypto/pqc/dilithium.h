#ifndef BITCOIN_CRYPTO_PQC_DILITHIUM_H
#define BITCOIN_CRYPTO_PQC_DILITHIUM_H

#include <stdint.h>
#include <vector>

namespace pqc {

/**
 * CRYSTALS-Dilithium / ML-DSA-44 digital signature scheme.
 *
 * Wraps the vendored pq-crystals ML-DSA-44 reference implementation.
 * The vendored configuration uses deterministic signing, which is required
 * for stable Bitcoin transaction signing behavior.
 *
 * Security level: NIST Level 2 (roughly equivalent to AES-128).
 */
class Dilithium {
public:
    static constexpr size_t PUBLIC_KEY_SIZE = 1312;
    static constexpr size_t PRIVATE_KEY_SIZE = 2560;
    static constexpr size_t SIGNATURE_SIZE = 2420;
    static constexpr size_t SEED_SIZE = 32;

    Dilithium();
    ~Dilithium();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool DeriveKeyPair(const std::vector<uint8_t>& seed, std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_DILITHIUM_H
