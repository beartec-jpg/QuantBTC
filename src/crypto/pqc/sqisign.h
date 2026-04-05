#ifndef BITCOIN_CRYPTO_PQC_SQISIGN_H
#define BITCOIN_CRYPTO_PQC_SQISIGN_H

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

class SQIsign {
public:
    static const size_t PUBLIC_KEY_SIZE = 64;    // SQIsign NIST Level 1
    static const size_t PRIVATE_KEY_SIZE = 16;   // SQIsign NIST Level 1
    static const size_t SIGNATURE_SIZE = 8864;   // SQIsign NIST Level 1

    SQIsign();
    ~SQIsign();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_SQISIGN_H
