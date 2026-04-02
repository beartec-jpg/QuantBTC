/*
 * CRYSTALS-Dilithium2 (ML-DSA-44) implementation.
 * Delegates to the pq-crystals reference C implementation under ml-dsa/.
 *
 * Key sizes (Dilithium2):
 *   Public key  : 1312 bytes
 *   Secret key  : 2560 bytes  (2*SEEDBYTES + TRBYTES + poly vectors)
 *   Signature   : 2420 bytes
 *
 * This replaces the former HMAC-SHA512 stub with real lattice cryptography.
 */

#include "dilithium.h"
#include <logging.h>
#include <support/cleanse.h>
#include <cstring>

/* Pull in the Dilithium2 reference implementation as C */
extern "C" {
#include "ml-dsa/params.h"
#include "ml-dsa/sign.h"
}

static_assert(pqc::Dilithium::PUBLIC_KEY_SIZE  == CRYPTO_PUBLICKEYBYTES,
              "Dilithium PUBLIC_KEY_SIZE mismatch with reference params");
static_assert(pqc::Dilithium::PRIVATE_KEY_SIZE == CRYPTO_SECRETKEYBYTES,
              "Dilithium PRIVATE_KEY_SIZE mismatch with reference params");
static_assert(pqc::Dilithium::SIGNATURE_SIZE   == CRYPTO_BYTES,
              "Dilithium SIGNATURE_SIZE mismatch with reference params");

namespace pqc {

Dilithium::Dilithium() {}
Dilithium::~Dilithium() {}

bool Dilithium::GenerateKeyPair(std::vector<uint8_t>& public_key,
                                 std::vector<uint8_t>& private_key)
{
    try {
        public_key.resize(PUBLIC_KEY_SIZE);
        private_key.resize(PRIVATE_KEY_SIZE);

        int ret = crypto_sign_keypair(public_key.data(), private_key.data());
        if (ret != 0) {
            LogPrintf("Dilithium::GenerateKeyPair: crypto_sign_keypair failed (%d)\n", ret);
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        LogPrintf("Dilithium::GenerateKeyPair: %s\n", e.what());
        return false;
    }
}

bool Dilithium::DeriveKeyPair(const std::vector<uint8_t>& seed,
                               std::vector<uint8_t>& public_key,
                               std::vector<uint8_t>& private_key)
{
    try {
        if (seed.size() < SEEDBYTES) {
            LogPrintf("Dilithium::DeriveKeyPair: seed too short (%u bytes, need %d)\n",
                      seed.size(), SEEDBYTES);
            return false;
        }

        public_key.resize(PUBLIC_KEY_SIZE);
        private_key.resize(PRIVATE_KEY_SIZE);

        int ret = crypto_sign_seed_keypair(public_key.data(), private_key.data(),
                                           seed.data());
        if (ret != 0) {
            LogPrintf("Dilithium::DeriveKeyPair: crypto_sign_seed_keypair failed (%d)\n", ret);
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        LogPrintf("Dilithium::DeriveKeyPair: %s\n", e.what());
        return false;
    }
}

bool Dilithium::Sign(const std::vector<uint8_t>& message,
                      const std::vector<uint8_t>& private_key,
                      std::vector<uint8_t>& signature)
{
    try {
        if (private_key.size() != PRIVATE_KEY_SIZE) {
            LogPrintf("Dilithium::Sign: wrong private key size (%u bytes)\n",
                      private_key.size());
            return false;
        }

        signature.resize(SIGNATURE_SIZE);
        size_t siglen = 0;

        /* ctx = NULL, ctxlen = 0 (no context string) */
        int ret = crypto_sign_signature(signature.data(), &siglen,
                                        message.data(), message.size(),
                                        nullptr, 0,
                                        private_key.data());
        if (ret != 0 || siglen != SIGNATURE_SIZE) {
            LogPrintf("Dilithium::Sign: signing failed (ret=%d, siglen=%u)\n",
                      ret, (unsigned)siglen);
            return false;
        }
        return true;
    } catch (const std::exception& e) {
        LogPrintf("Dilithium::Sign: %s\n", e.what());
        return false;
    }
}

bool Dilithium::Verify(const std::vector<uint8_t>& message,
                        const std::vector<uint8_t>& signature,
                        const std::vector<uint8_t>& public_key)
{
    try {
        if (public_key.size() != PUBLIC_KEY_SIZE) {
            LogPrintf("Dilithium::Verify: wrong public key size (%u bytes)\n",
                      public_key.size());
            return false;
        }
        if (signature.size() != SIGNATURE_SIZE) {
            LogPrintf("Dilithium::Verify: wrong signature size (%u bytes)\n",
                      signature.size());
            return false;
        }

        /* ctx = NULL, ctxlen = 0 (no context string) */
        int ret = crypto_sign_verify(signature.data(), signature.size(),
                                     message.data(), message.size(),
                                     nullptr, 0,
                                     public_key.data());
        return (ret == 0);
    } catch (const std::exception& e) {
        LogPrintf("Dilithium::Verify: %s\n", e.what());
        return false;
    }
}

} // namespace pqc
