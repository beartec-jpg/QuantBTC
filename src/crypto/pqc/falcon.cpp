// Falcon-padded-512 / FN-DSA digital signature implementation.
// Wraps the vendored PQClean Falcon-padded-512 reference implementation.
// Domain context string separates QuantBTC Falcon sigs from other applications.
#include "falcon.h"

#include <logging.h>
#include <support/cleanse.h>

extern "C" {
#include <crypto/pqc/falcon-padded/api.h>
}

// Compile-time guards: our constants must match the vendored library.
static_assert(pqc::Falcon::PUBLIC_KEY_SIZE  == PQCLEAN_FALCONPADDED512_CLEAN_CRYPTO_PUBLICKEYBYTES,
              "Falcon PUBLIC_KEY_SIZE mismatch with vendored library");
static_assert(pqc::Falcon::PRIVATE_KEY_SIZE == PQCLEAN_FALCONPADDED512_CLEAN_CRYPTO_SECRETKEYBYTES,
              "Falcon PRIVATE_KEY_SIZE mismatch with vendored library");
static_assert(pqc::Falcon::SIGNATURE_SIZE   == PQCLEAN_FALCONPADDED512_CLEAN_CRYPTO_BYTES,
              "Falcon SIGNATURE_SIZE mismatch with vendored library");

namespace pqc {

/*
 * Application context string for domain separation.
 * Ensures QuantBTC Falcon signatures are not replayable across other
 * applications using the same key. Changing this is consensus-breaking.
 */
static const uint8_t FALCON_CTX[]     = "QuantBTC-Falcon-v1";
static const size_t  FALCON_CTX_LEN   = sizeof(FALCON_CTX) - 1;

Falcon::Falcon() {}
Falcon::~Falcon() {}

bool Falcon::GenerateKeyPair(std::vector<uint8_t>& public_key,
                             std::vector<uint8_t>& private_key)
{
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (PQCLEAN_FALCONPADDED512_CLEAN_crypto_sign_keypair(
            public_key.data(), private_key.data()) != 0) {
        LogPrintf("Falcon::GenerateKeyPair: keypair generation failed\n");
        memory_cleanse(public_key.data(), public_key.size());
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }
    return true;
}

bool Falcon::DeriveKeyPair(const std::vector<uint8_t>& seed,
                           std::vector<uint8_t>& public_key,
                           std::vector<uint8_t>& private_key)
{
    if (seed.size() != SEED_SIZE) {
        LogPrintf("Falcon::DeriveKeyPair: invalid seed size (%u, expected %u)\n",
                  seed.size(), SEED_SIZE);
        return false;
    }

    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (PQCLEAN_FALCONPADDED512_CLEAN_crypto_sign_seed_keypair(
            public_key.data(), private_key.data(), seed.data()) != 0) {
        LogPrintf("Falcon::DeriveKeyPair: seeded keypair generation failed\n");
        memory_cleanse(public_key.data(), public_key.size());
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }
    return true;
}

bool Falcon::Sign(const std::vector<uint8_t>& message,
                  const std::vector<uint8_t>& private_key,
                  std::vector<uint8_t>& signature)
{
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        LogPrintf("Falcon::Sign: invalid private key size (%u, expected %u)\n",
                  private_key.size(), PRIVATE_KEY_SIZE);
        return false;
    }

    // Prepend context string to message for domain separation.
    std::vector<uint8_t> msg_with_ctx;
    msg_with_ctx.reserve(FALCON_CTX_LEN + message.size());
    msg_with_ctx.insert(msg_with_ctx.end(), FALCON_CTX, FALCON_CTX + FALCON_CTX_LEN);
    msg_with_ctx.insert(msg_with_ctx.end(), message.begin(), message.end());

    signature.resize(SIGNATURE_SIZE);
    size_t siglen = 0;

    if (PQCLEAN_FALCONPADDED512_CLEAN_crypto_sign_signature(
            signature.data(), &siglen,
            msg_with_ctx.data(), msg_with_ctx.size(),
            private_key.data()) != 0) {
        LogPrintf("Falcon::Sign: signing failed\n");
        memory_cleanse(signature.data(), signature.size());
        signature.clear();
        return false;
    }

    // PQClean padded variant always produces exactly SIGNATURE_SIZE bytes.
    if (siglen != SIGNATURE_SIZE) {
        LogPrintf("Falcon::Sign: unexpected signature length %u (expected %u)\n",
                  siglen, SIGNATURE_SIZE);
        memory_cleanse(signature.data(), signature.size());
        signature.clear();
        return false;
    }
    return true;
}

bool Falcon::Verify(const std::vector<uint8_t>& message,
                    const std::vector<uint8_t>& signature,
                    const std::vector<uint8_t>& public_key)
{
    if (signature.size() != SIGNATURE_SIZE) {
        LogPrintf("Falcon::Verify: wrong signature size (%u, expected %u)\n",
                  signature.size(), SIGNATURE_SIZE);
        return false;
    }
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        LogPrintf("Falcon::Verify: wrong public key size (%u, expected %u)\n",
                  public_key.size(), PUBLIC_KEY_SIZE);
        return false;
    }

    // Recreate the same context-prepended message used during signing.
    std::vector<uint8_t> msg_with_ctx;
    msg_with_ctx.reserve(FALCON_CTX_LEN + message.size());
    msg_with_ctx.insert(msg_with_ctx.end(), FALCON_CTX, FALCON_CTX + FALCON_CTX_LEN);
    msg_with_ctx.insert(msg_with_ctx.end(), message.begin(), message.end());

    return PQCLEAN_FALCONPADDED512_CLEAN_crypto_sign_verify(
               signature.data(), signature.size(),
               msg_with_ctx.data(), msg_with_ctx.size(),
               public_key.data()) == 0;
}

} // namespace pqc

// ─────────────────────────────────────────────────────────────────────────────
// Falcon1024 implementation — PQClean FALCONPADDED1024_CLEAN
// ─────────────────────────────────────────────────────────────────────────────

extern "C" {
#include <crypto/pqc/falcon-padded-1024/api.h>
}

static_assert(pqc::Falcon1024::PUBLIC_KEY_SIZE  == PQCLEAN_FALCONPADDED1024_CLEAN_CRYPTO_PUBLICKEYBYTES,
              "Falcon1024 PUBLIC_KEY_SIZE mismatch with vendored library");
static_assert(pqc::Falcon1024::PRIVATE_KEY_SIZE == PQCLEAN_FALCONPADDED1024_CLEAN_CRYPTO_SECRETKEYBYTES,
              "Falcon1024 PRIVATE_KEY_SIZE mismatch with vendored library");
static_assert(pqc::Falcon1024::SIGNATURE_SIZE   == PQCLEAN_FALCONPADDED1024_CLEAN_CRYPTO_BYTES,
              "Falcon1024 SIGNATURE_SIZE mismatch with vendored library");

namespace pqc {

Falcon1024::Falcon1024() = default;
Falcon1024::~Falcon1024() = default;

bool Falcon1024::GenerateKeyPair(std::vector<uint8_t>& public_key,
                                 std::vector<uint8_t>& private_key)
{
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);
    int rc = PQCLEAN_FALCONPADDED1024_CLEAN_crypto_sign_keypair(
                 public_key.data(), private_key.data());
    if (rc != 0) {
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }
    return true;
}

bool Falcon1024::DeriveKeyPair(const std::vector<uint8_t>& seed,
                                std::vector<uint8_t>& public_key,
                                std::vector<uint8_t>& private_key)
{
    if (seed.size() != SEED_SIZE) {
        LogPrintf("Falcon1024::DeriveKeyPair: wrong seed size (%u, expected %u)\n",
                  seed.size(), SEED_SIZE);
        return false;
    }
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);
    int rc = PQCLEAN_FALCONPADDED1024_CLEAN_crypto_sign_seed_keypair(
                 public_key.data(), private_key.data(), seed.data());
    if (rc != 0) {
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }
    return true;
}

bool Falcon1024::Sign(const std::vector<uint8_t>& message,
                      const std::vector<uint8_t>& private_key,
                      std::vector<uint8_t>& signature)
{
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        LogPrintf("Falcon1024::Sign: wrong private key size (%u, expected %u)\n",
                  private_key.size(), PRIVATE_KEY_SIZE);
        return false;
    }
    // Prepend the same domain context as Falcon-512 for namespace separation.
    std::vector<uint8_t> msg_with_ctx;
    msg_with_ctx.reserve(FALCON_CTX_LEN + message.size());
    msg_with_ctx.insert(msg_with_ctx.end(), FALCON_CTX, FALCON_CTX + FALCON_CTX_LEN);
    msg_with_ctx.insert(msg_with_ctx.end(), message.begin(), message.end());

    signature.resize(SIGNATURE_SIZE);
    size_t siglen = SIGNATURE_SIZE;
    int rc = PQCLEAN_FALCONPADDED1024_CLEAN_crypto_sign_signature(
                 signature.data(), &siglen,
                 msg_with_ctx.data(), msg_with_ctx.size(),
                 private_key.data());
    if (rc != 0 || siglen != SIGNATURE_SIZE) {
        signature.clear();
        return false;
    }
    return true;
}

bool Falcon1024::Verify(const std::vector<uint8_t>& message,
                        const std::vector<uint8_t>& signature,
                        const std::vector<uint8_t>& public_key)
{
    if (signature.size() != SIGNATURE_SIZE) {
        LogPrintf("Falcon1024::Verify: wrong signature size (%u, expected %u)\n",
                  signature.size(), SIGNATURE_SIZE);
        return false;
    }
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        LogPrintf("Falcon1024::Verify: wrong public key size (%u, expected %u)\n",
                  public_key.size(), PUBLIC_KEY_SIZE);
        return false;
    }
    std::vector<uint8_t> msg_with_ctx;
    msg_with_ctx.reserve(FALCON_CTX_LEN + message.size());
    msg_with_ctx.insert(msg_with_ctx.end(), FALCON_CTX, FALCON_CTX + FALCON_CTX_LEN);
    msg_with_ctx.insert(msg_with_ctx.end(), message.begin(), message.end());

    return PQCLEAN_FALCONPADDED1024_CLEAN_crypto_sign_verify(
               signature.data(), signature.size(),
               msg_with_ctx.data(), msg_with_ctx.size(),
               public_key.data()) == 0;
}

} // namespace pqc
