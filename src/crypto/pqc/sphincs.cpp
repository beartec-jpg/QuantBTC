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

#include <oqs/oqs.h>

/**
 * SPHINCS+ / SLH-DSA-SHA2-128f — real NIST FIPS 205 implementation via liboqs.
 *
 * Hash-based stateless signature scheme. Security relies only on the
 * collision resistance of SHA-256, making it the most conservative
 * post-quantum signature scheme available.
 */

namespace pqc {

SPHINCS::SPHINCS() {}
SPHINCS::~SPHINCS() {}

bool SPHINCS::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_sphincs_sha2_128f_simple);
    if (!sig) {
        LogPrintf("SPHINCS::GenerateKeyPair: OQS_SIG_new failed\n");
        return false;
    }

    public_key.resize(sig->length_public_key);
    private_key.resize(sig->length_secret_key);

    OQS_STATUS rc = OQS_SIG_keypair(sig, public_key.data(), private_key.data());
    OQS_SIG_free(sig);

    if (rc != OQS_SUCCESS) {
        LogPrintf("SPHINCS::GenerateKeyPair: OQS_SIG_keypair failed\n");
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

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_sphincs_sha2_128f_simple);
    if (!sig) {
        LogPrintf("SPHINCS::Sign: OQS_SIG_new failed\n");
        return false;
    }

    signature.resize(sig->length_signature);
    size_t sig_len = 0;

    OQS_STATUS rc = OQS_SIG_sign(sig,
                                  signature.data(), &sig_len,
                                  message.data(), message.size(),
                                  private_key.data());
    OQS_SIG_free(sig);

    if (rc != OQS_SUCCESS) {
        LogPrintf("SPHINCS::Sign: OQS_SIG_sign failed\n");
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

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_sphincs_sha2_128f_simple);
    if (!sig) {
        LogPrintf("SPHINCS::Verify: OQS_SIG_new failed\n");
        return false;
    }

    OQS_STATUS rc = OQS_SIG_verify(sig,
                                    message.data(), message.size(),
                                    signature.data(), signature.size(),
                                    public_key.data());
    OQS_SIG_free(sig);

    return (rc == OQS_SUCCESS);
}

} // namespace pqc
