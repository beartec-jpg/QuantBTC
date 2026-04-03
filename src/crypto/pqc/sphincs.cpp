#include "sphincs.h"
#include <logging.h>
#include <random.h>
#include <span.h>
#include <support/cleanse.h>

/* Provide the randombytes() function required by the SPHINCS+ reference
 * implementation using Bitcoin Core's cryptographically secure RNG. */
extern "C" {
void randombytes(unsigned char* x, unsigned long long xlen) {
    GetRandBytes(Span<unsigned char>(x, static_cast<size_t>(xlen)));
}
} // extern "C"

/* Include the SPHINCS+ (SLH-DSA-SHA2-128f) reference implementation API. */
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
    try {
        public_key.resize(PUBLIC_KEY_SIZE);
        private_key.resize(PRIVATE_KEY_SIZE);

        int ret = crypto_sign_keypair(public_key.data(), private_key.data());
        if (ret != 0) {
            LogPrintf("SPHINCS::GenerateKeyPair: crypto_sign_keypair failed (%d)\n", ret);
            memory_cleanse(private_key.data(), private_key.size());
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        LogPrintf("SPHINCS::GenerateKeyPair: %s\n", e.what());
        memory_cleanse(private_key.data(), private_key.size());
        return false;
    }
}

bool SPHINCS::Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature) {
    try {
        if (private_key.size() != PRIVATE_KEY_SIZE) {
            LogPrintf("SPHINCS::Sign: invalid private key size %zu\n", private_key.size());
            return false;
        }

        signature.resize(SIGNATURE_SIZE);
        size_t siglen = 0;

        int ret = crypto_sign_signature(
            signature.data(), &siglen,
            message.data(), message.size(),
            private_key.data());

        if (ret != 0) {
            LogPrintf("SPHINCS::Sign: crypto_sign_signature failed (%d)\n", ret);
            memory_cleanse(signature.data(), signature.size());
            return false;
        }

        signature.resize(siglen);
        return true;
    } catch (const std::exception& e) {
        LogPrintf("SPHINCS::Sign: %s\n", e.what());
        memory_cleanse(signature.data(), signature.size());
        return false;
    }
}

bool SPHINCS::Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key) {
    try {
        if (public_key.size() != PUBLIC_KEY_SIZE) {
            LogPrintf("SPHINCS::Verify: invalid public key size %zu\n", public_key.size());
            return false;
        }
        // SPHINCS+ reference implementations always produce SIGNATURE_SIZE bytes,
        // but optimized implementations may emit shorter signatures.  We accept
        // any non-empty signature up to the maximum; crypto_sign_verify performs
        // full cryptographic validation of the actual signature content.
        if (signature.empty() || signature.size() > SIGNATURE_SIZE) {
            LogPrintf("SPHINCS::Verify: invalid signature size %zu\n", signature.size());
            return false;
        }

        int ret = crypto_sign_verify(
            signature.data(), signature.size(),
            message.data(), message.size(),
            public_key.data());

        return ret == 0;
    } catch (const std::exception& e) {
        LogPrintf("SPHINCS::Verify: %s\n", e.what());
        return false;
    }
}

} // namespace pqc
