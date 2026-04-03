#ifndef BITCOIN_CRYPTO_PQC_SPHINCS_H
#define BITCOIN_CRYPTO_PQC_SPHINCS_H

#include <stdint.h>
#include <vector>

namespace pqc {

/**
 * SPHINCS+ / SLH-DSA-SHA2-128f digital signature scheme.
 *
 * Wraps the vendored pq-crystals SPHINCS+ reference implementation
 * (NIST FIPS 205 / SLH-DSA, SHA2-128f-simple parameter set).
 *
 * Security level: NIST Level 1 (roughly equivalent to AES-128).
 * Hash-based (stateless) — security does not depend on lattice assumptions.
 */
class SPHINCS {
public:
    // SLH-DSA-SHA2-128f-simple sizes (from sphincsplus/params.h):
    //   SPX_N = 16, SPX_PK_BYTES = 2*N = 32, SPX_SK_BYTES = 2*N + PK = 64
    //   SPX_BYTES (signature) = 17088
    static constexpr size_t PUBLIC_KEY_SIZE  = 32;
    static constexpr size_t PRIVATE_KEY_SIZE = 64;
    static constexpr size_t SIGNATURE_SIZE   = 17088;

    SPHINCS();
    ~SPHINCS();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_SPHINCS_H
