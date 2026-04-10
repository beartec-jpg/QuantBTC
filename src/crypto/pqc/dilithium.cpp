#include "dilithium.h"

#include <logging.h>
#include <support/cleanse.h>

extern "C" {
#include <crypto/pqc/ml-dsa/sign.h>
#include <crypto/pqc/ml-dsa/params.h>
}

// Compile-time guards: ensure our constants match the vendored library.
static_assert(pqc::Dilithium::PUBLIC_KEY_SIZE  == CRYPTO_PUBLICKEYBYTES, "Dilithium PUBLIC_KEY_SIZE mismatch");
static_assert(pqc::Dilithium::PRIVATE_KEY_SIZE == CRYPTO_SECRETKEYBYTES, "Dilithium PRIVATE_KEY_SIZE mismatch");
static_assert(pqc::Dilithium::SIGNATURE_SIZE   == CRYPTO_BYTES,          "Dilithium SIGNATURE_SIZE mismatch");

namespace pqc {

Dilithium::Dilithium() {}
Dilithium::~Dilithium() {}

bool Dilithium::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key)
{
    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (crypto_sign_keypair(public_key.data(), private_key.data()) != 0) {
        LogPrintf("Dilithium::GenerateKeyPair: crypto_sign_keypair failed\n");
        memory_cleanse(public_key.data(), public_key.size());
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }

    return true;
}

bool Dilithium::DeriveKeyPair(const std::vector<uint8_t>& seed,
                              std::vector<uint8_t>& public_key,
                              std::vector<uint8_t>& private_key)
{
    if (seed.size() != SEED_SIZE) {
        LogPrintf("Dilithium::DeriveKeyPair: invalid seed size (%u, expected %u)\n",
                  seed.size(), SEED_SIZE);
        return false;
    }

    public_key.resize(PUBLIC_KEY_SIZE);
    private_key.resize(PRIVATE_KEY_SIZE);

    if (crypto_sign_seed_keypair(public_key.data(), private_key.data(), seed.data()) != 0) {
        LogPrintf("Dilithium::DeriveKeyPair: crypto_sign_seed_keypair failed\n");
        memory_cleanse(public_key.data(), public_key.size());
        memory_cleanse(private_key.data(), private_key.size());
        public_key.clear();
        private_key.clear();
        return false;
    }

    return true;
}

bool Dilithium::Sign(const std::vector<uint8_t>& message,
                     const std::vector<uint8_t>& private_key,
                     std::vector<uint8_t>& signature)
{
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        LogPrintf("Dilithium::Sign: invalid private key size (%u, expected %u)\n",
                  private_key.size(), PRIVATE_KEY_SIZE);
        return false;
    }

    signature.resize(SIGNATURE_SIZE);
    size_t sig_len = 0;
    if (crypto_sign_signature(signature.data(), &sig_len,
                              message.data(), message.size(),
                              nullptr, 0,
                              private_key.data()) != 0) {
        LogPrintf("Dilithium::Sign: crypto_sign_signature failed\n");
        signature.clear();
        return false;
    }

    if (sig_len != SIGNATURE_SIZE) {
        LogPrintf("Dilithium::Sign: unexpected signature length %u (expected %u)\n",
                  sig_len, SIGNATURE_SIZE);
        signature.clear();
        return false;
    }

    return true;
}

bool Dilithium::Verify(const std::vector<uint8_t>& message,
                       const std::vector<uint8_t>& signature,
                       const std::vector<uint8_t>& public_key)
{
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        return false;
    }
    if (signature.size() != SIGNATURE_SIZE) {
        return false;
    }

    return crypto_sign_verify(signature.data(), signature.size(),
                              message.data(), message.size(),
                              nullptr, 0,
                              public_key.data()) == 0;
}

} // namespace pqc
