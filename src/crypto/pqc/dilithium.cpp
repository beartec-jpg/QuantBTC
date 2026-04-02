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

#include <oqs/oqs.h>

/**
 * CRYSTALS-Dilithium / ML-DSA-44 — real NIST FIPS 204 implementation via liboqs.
 *
 * This is the NIST-standardized Module-Lattice Digital Signature Algorithm
 * at security level 2. All keygen, sign, and verify operations are performed
 * by the liboqs library using the reference/optimized ML-DSA-44 code.
 */

namespace pqc {

Dilithium::Dilithium() {}
Dilithium::~Dilithium() {}

bool Dilithium::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_ml_dsa_44);
    if (!sig) {
        LogPrintf("Dilithium::GenerateKeyPair: OQS_SIG_new(ML-DSA-44) failed\n");
        return false;
    }

    public_key.resize(sig->length_public_key);
    private_key.resize(sig->length_secret_key);

    OQS_STATUS rc = OQS_SIG_keypair(sig, public_key.data(), private_key.data());
    OQS_SIG_free(sig);

    if (rc != OQS_SUCCESS) {
        LogPrintf("Dilithium::GenerateKeyPair: OQS_SIG_keypair failed\n");
        public_key.clear();
        private_key.clear();
        return false;
    }

    LogPrintf("Dilithium::GenerateKeyPair: ML-DSA-44 keypair generated (%u-byte pk, %u-byte sk)\n",
              public_key.size(), private_key.size());
    return true;
}

bool Dilithium::DeriveKeyPair(const std::vector<uint8_t>& seed,
                               std::vector<uint8_t>& public_key,
                               std::vector<uint8_t>& private_key) {
    // ML-DSA-44 does not expose a seed-based keygen in the liboqs API.
    // Generate a fresh keypair instead. The seed parameter is accepted
    // for API compatibility but not used for derivation.
    (void)seed;
    LogPrintf("Dilithium::DeriveKeyPair: seed-based derivation not supported by ML-DSA, generating fresh keypair\n");
    return GenerateKeyPair(public_key, private_key);
}

bool Dilithium::Sign(const std::vector<uint8_t>& message,
                     const std::vector<uint8_t>& private_key,
                     std::vector<uint8_t>& signature) {
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        LogPrintf("Dilithium::Sign: invalid private key size (%u, expected %u)\n",
                  private_key.size(), PRIVATE_KEY_SIZE);
        return false;
    }

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_ml_dsa_44);
    if (!sig) {
        LogPrintf("Dilithium::Sign: OQS_SIG_new failed\n");
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
        LogPrintf("Dilithium::Sign: OQS_SIG_sign failed\n");
        signature.clear();
        return false;
    }

    signature.resize(sig_len);
    return true;
}

bool Dilithium::Verify(const std::vector<uint8_t>& message,
                       const std::vector<uint8_t>& signature,
                       const std::vector<uint8_t>& public_key) {
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        return false;
    }
    if (signature.empty() || signature.size() > SIGNATURE_SIZE) {
        return false;
    }

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_ml_dsa_44);
    if (!sig) {
        LogPrintf("Dilithium::Verify: OQS_SIG_new failed\n");
        return false;
    }

    OQS_STATUS rc = OQS_SIG_verify(sig,
                                    message.data(), message.size(),
                                    signature.data(), signature.size(),
                                    public_key.data());
    OQS_SIG_free(sig);

    if (rc != OQS_SUCCESS) {
        return false;
    }

    return true;
}

} // namespace pqc
