#include "sphincs.h"
#include <logging.h>

/* randombytes() is provided by the canonical definition in
 * crypto/pqc/ml-dsa/randombytes.cpp with GetStrongRandBytes.  */

/* Include the vendored SPHINCS+ (SLH-DSA-SHA2-128f) reference implementation. */
extern "C" {
#include "sphincsplus/api.h"
} // extern "C"

static_assert(pqc::SPHINCS::PUBLIC_KEY_SIZE  == CRYPTO_PUBLICKEYBYTES,
              "SPHINCS PUBLIC_KEY_SIZE mismatch with reference params");
static_assert(pqc::SPHINCS::PRIVATE_KEY_SIZE == CRYPTO_SECRETKEYBYTES,
              "SPHINCS PRIVATE_KEY_SIZE mismatch with reference params");
static_assert(pqc::SPHINCS::SIGNATURE_SIZE   == CRYPTO_BYTES,
              "SPHINCS SIGNATURE_SIZE mismatch with reference params");

namespace pqc {

SPHINCS::SPHINCS() {}
SPHINCS::~SPHINCS() {}

bool SPHINCS::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (crypto_sign_keypair(public_key.data(), private_key.data()) != 0) {
        LogPrintf("SPHINCS::GenerateKeyPair: crypto_sign_keypair failed\n");
        public_key.clear();
        private_key.clear();
        return false;
    }

    return true;
}

bool SPHINCS::Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature) {
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        return false;
    }

    signature.resize(SIGNATURE_SIZE);
    size_t sig_len = 0;

    if (crypto_sign_signature(signature.data(), &sig_len,
                              message.data(), message.size(),
                              private_key.data()) != 0) {
        LogPrintf("SPHINCS::Sign: crypto_sign_signature failed\n");
        signature.clear();
        return false;
    }

    signature.resize(sig_len);
    return true;
}

bool SPHINCS::Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key) {
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        return false;
    }

    return crypto_sign_verify(signature.data(), signature.size(),
                              message.data(), message.size(),
                              public_key.data()) == 0;
}

} // namespace pqc
