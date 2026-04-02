#ifndef BITCOIN_CRYPTO_PQC_SPHINCS_H
#define BITCOIN_CRYPTO_PQC_SPHINCS_H

#include <stdint.h>
#include <vector>

#include <oqs/oqs.h>

namespace pqc {

/**
 * SPHINCS+ / SLH-DSA-SHA2-128f digital signature scheme.
 *
 * Wraps liboqs implementation of NIST FIPS 205 (SLH-DSA).
 * Uses the SHA2-128f-simple parameter set for fast signing.
 *
 * Security level: NIST Level 1 (roughly equivalent to AES-128).
 * Hash-based (stateless) — security does not depend on lattice assumptions.
 */
class SPHINCS {
public:
    static constexpr size_t PUBLIC_KEY_SIZE = OQS_SIG_sphincs_sha2_128f_simple_length_public_key;    // 32
    static constexpr size_t PRIVATE_KEY_SIZE = OQS_SIG_sphincs_sha2_128f_simple_length_secret_key;   // 64
    static constexpr size_t SIGNATURE_SIZE = OQS_SIG_sphincs_sha2_128f_simple_length_signature;      // 17088

    SPHINCS();
    ~SPHINCS();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_SPHINCS_H
