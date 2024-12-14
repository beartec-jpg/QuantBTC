#ifndef BITCOIN_CRYPTO_PQC_SPHINCS_H
#define BITCOIN_CRYPTO_PQC_SPHINCS_H

#include <stdint.h>
#include <vector>

namespace pqc {

class SPHINCS {
public:
    static const size_t PUBLIC_KEY_SIZE = 32;  // Adjust sizes based on specific SPHINCS+ parameter set
    static const size_t PRIVATE_KEY_SIZE = 64;
    static const size_t SIGNATURE_SIZE = 8080;  // For SPHINCS+-128f

    SPHINCS();
    ~SPHINCS();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_SPHINCS_H
