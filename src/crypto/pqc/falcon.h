#ifndef BITCOIN_CRYPTO_PQC_FALCON_H
#define BITCOIN_CRYPTO_PQC_FALCON_H

// ============================================================================
// NOT PRODUCTION — STUB ONLY
// WARNING: THIS ALGORITHM IS NOT IMPLEMENTED
// All methods return false. Do NOT use until a real implementation is integrated.
// Do NOT deploy this file in production builds.
// See TODO.md for implementation status.
// ============================================================================

#include <stdint.h>
#include <vector>

#include <oqs/oqs.h>

namespace pqc {

/**
 * Falcon-padded-512 / FN-DSA digital signature scheme.
 *
 * Wraps liboqs implementation. Uses the padded variant for fixed-size
 * signatures (666 bytes), which simplifies consensus-layer size checks.
 *
 * Security level: NIST Level 1 (roughly equivalent to AES-128).
 * Based on NTRU lattices with fast Fourier sampling.
 */
class Falcon {
public:
    static constexpr size_t PUBLIC_KEY_SIZE = OQS_SIG_falcon_padded_512_length_public_key;    // 897
    static constexpr size_t PRIVATE_KEY_SIZE = OQS_SIG_falcon_padded_512_length_secret_key;   // 1281
    static constexpr size_t SIGNATURE_SIZE = OQS_SIG_falcon_padded_512_length_signature;      // 666

    Falcon();
    ~Falcon();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_FALCON_H
