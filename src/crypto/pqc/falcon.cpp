// NOT PRODUCTION — STUB ONLY: Falcon is not implemented; all methods return false.
#include "falcon.h"
#include <logging.h>

#include <oqs/oqs.h>

/**
 * Falcon-padded-512 / FN-DSA — real implementation via liboqs.
 *
 * NTRU-lattice-based signature scheme selected by NIST for standardization
 * as FN-DSA. Uses the padded variant for deterministic signature sizes.
 */

namespace pqc {

Falcon::Falcon() {}
Falcon::~Falcon() {}

bool Falcon::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_falcon_padded_512);
    if (!sig) {
        LogPrintf("Falcon::GenerateKeyPair: OQS_SIG_new failed\n");
        return false;
    }

    public_key.resize(sig->length_public_key);
    private_key.resize(sig->length_secret_key);

    OQS_STATUS rc = OQS_SIG_keypair(sig, public_key.data(), private_key.data());
    OQS_SIG_free(sig);

    if (rc != OQS_SUCCESS) {
        LogPrintf("Falcon::GenerateKeyPair: OQS_SIG_keypair failed\n");
        public_key.clear();
        private_key.clear();
        return false;
    }

    return true;
}

bool Falcon::Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature) {
    if (private_key.size() != PRIVATE_KEY_SIZE) {
        return false;
    }

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_falcon_padded_512);
    if (!sig) {
        LogPrintf("Falcon::Sign: OQS_SIG_new failed\n");
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
        LogPrintf("Falcon::Sign: OQS_SIG_sign failed\n");
        signature.clear();
        return false;
    }

    signature.resize(sig_len);
    return true;
}

bool Falcon::Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key) {
    if (public_key.size() != PUBLIC_KEY_SIZE) {
        return false;
    }

    OQS_SIG* sig = OQS_SIG_new(OQS_SIG_alg_falcon_padded_512);
    if (!sig) {
        LogPrintf("Falcon::Verify: OQS_SIG_new failed\n");
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
