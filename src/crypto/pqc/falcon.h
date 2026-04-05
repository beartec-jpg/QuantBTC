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
#include <cstddef>
#include <vector>

namespace pqc {

/**
 * Falcon-padded-512 / FN-DSA digital signature scheme — STUB.
 *
 * All operations return false. A real implementation will be wired in
 * when Falcon/FN-DSA support is enabled. The previous liboqs dependency
 * has been removed to allow builds without installing liboqs.
 *
 * Security level: NIST Level 1 (roughly equivalent to AES-128).
 * Based on NTRU lattices with fast Fourier sampling.
 */
class Falcon {
public:
    static constexpr size_t PUBLIC_KEY_SIZE = 897;    // Falcon-padded-512 public key
    static constexpr size_t PRIVATE_KEY_SIZE = 1281;  // Falcon-padded-512 secret key
    static constexpr size_t SIGNATURE_SIZE = 666;     // Falcon-padded-512 signature

    Falcon();
    ~Falcon();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_FALCON_H
