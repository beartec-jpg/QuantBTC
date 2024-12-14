#ifndef BITCOIN_CRYPTO_PQC_SQISIGN_H
#define BITCOIN_CRYPTO_PQC_SQISIGN_H

#include <stdint.h>
#include <vector>

namespace pqc {

class SQIsign {
public:
    static const size_t PUBLIC_KEY_SIZE = 64;    // Sizes to be adjusted based on final parameters
    static const size_t PRIVATE_KEY_SIZE = 32;
    static const size_t SIGNATURE_SIZE = 204;

    SQIsign();
    ~SQIsign();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_SQISIGN_H
