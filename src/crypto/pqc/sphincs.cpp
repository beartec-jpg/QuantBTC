#include "sphincs.h"
#include <logging.h>
#include <support/cleanse.h>

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

/**
 * SLH-DSA (SPHINCS+) application context string for domain separation.
 *
 * The SPHINCS+ reference implementation's `crypto_sign_signature` API does not
 * accept a context parameter (unlike ML-DSA-44).  We achieve the same domain
 * separation by prepending this fixed prefix to every message before it is
 * passed to the signing / verification functions.  This ensures that
 * QuantBTC SLH-DSA signatures are structurally distinguishable from
 * signatures produced by any other application using the same key and the
 * same SLH-DSA-SHA2-128f parameter set, preventing cross-protocol replay.
 *
 * CONSENSUS NOTE: The same prefix MUST be used in both Sign() and Verify().
 * Changing this string is a consensus-breaking change and must be coordinated
 * with an activation height.  The ML-DSA equivalent is MLDSA_CTX in dilithium.cpp.
 */
static constexpr char   SLHDSA_CTX[]    = "QuantBTC-SLH-DSA-v1";
static constexpr size_t SLHDSA_CTX_LEN  = sizeof(SLHDSA_CTX) - 1; // exclude NUL terminator

SPHINCS::SPHINCS() {}
SPHINCS::~SPHINCS() {}

bool SPHINCS::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (crypto_sign_keypair(public_key.data(), private_key.data()) != 0) {
        LogPrintf("SPHINCS::GenerateKeyPair: crypto_sign_keypair failed\n");
        memory_cleanse(public_key.data(), public_key.size());
        memory_cleanse(private_key.data(), private_key.size());
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

    // Prepend the domain-separation context to the message.
    // See SLHDSA_CTX comment above for rationale.
    std::vector<uint8_t> prefixed;
    prefixed.reserve(SLHDSA_CTX_LEN + message.size());
    prefixed.insert(prefixed.end(), SLHDSA_CTX, SLHDSA_CTX + SLHDSA_CTX_LEN);
    prefixed.insert(prefixed.end(), message.begin(), message.end());

    signature.resize(SIGNATURE_SIZE);
    size_t sig_len = 0;

    if (crypto_sign_signature(signature.data(), &sig_len,
                              prefixed.data(), prefixed.size(),
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
    if (signature.size() != SIGNATURE_SIZE) {
        return false;
    }

    // Prepend the domain-separation context to the message (must match Sign).
    std::vector<uint8_t> prefixed;
    prefixed.reserve(SLHDSA_CTX_LEN + message.size());
    prefixed.insert(prefixed.end(), SLHDSA_CTX, SLHDSA_CTX + SLHDSA_CTX_LEN);
    prefixed.insert(prefixed.end(), message.begin(), message.end());

    return crypto_sign_verify(signature.data(), signature.size(),
                              prefixed.data(), prefixed.size(),
                              public_key.data()) == 0;
}

} // namespace pqc
