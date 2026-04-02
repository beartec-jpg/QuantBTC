/*
 * ML-KEM-768 (Kyber-768) implementation.
 * Delegates to the pq-crystals/kyber reference C implementation under ml-kem/.
 *
 * Key sizes (Kyber-768):
 *   Public key  : 1184 bytes
 *   Secret key  : 2400 bytes
 *   Ciphertext  : 1088 bytes
 *   Shared secret: 32 bytes
 *
 * This replaces the former broken toy implementation with the real
 * IND-CCA2-secure KEM including the Fujisaki-Okamoto transform.
 */

#include "kyber.h"
#include <logging.h>
#include <string.h>

#include <oqs/oqs.h>

/**
 * ML-KEM-768 — real NIST FIPS 203 implementation via liboqs.
 *
 * This is the NIST-standardized Module-Lattice Key Encapsulation Mechanism
 * at security level 3. All keygen, encaps, and decaps operations are
 * performed by the liboqs library.
 */

namespace pqc {

bool Kyber::KeyGen(unsigned char *pk, unsigned char *sk) {
    OQS_KEM* kem = OQS_KEM_new(OQS_KEM_alg_ml_kem_768);
    if (!kem) {
        LogPrintf("Kyber::KeyGen: OQS_KEM_new(ML-KEM-768) failed\n");
        return false;
    }

    OQS_STATUS rc = OQS_KEM_keypair(kem, pk, sk);
    OQS_KEM_free(kem);

    if (rc != OQS_SUCCESS) {
        LogPrintf("Kyber::KeyGen: OQS_KEM_keypair failed\n");
        return false;
    }

    return true;
}

bool Kyber::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    OQS_KEM* kem = OQS_KEM_new(OQS_KEM_alg_ml_kem_768);
    if (!kem) {
        LogPrintf("Kyber::Encaps: OQS_KEM_new(ML-KEM-768) failed\n");
        return false;
    }

    OQS_STATUS rc = OQS_KEM_encaps(kem, ct, ss, pk);
    OQS_KEM_free(kem);

    if (rc != OQS_SUCCESS) {
        LogPrintf("Kyber::Encaps: OQS_KEM_encaps failed\n");
        return false;
    }

    return true;
}

bool Kyber::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    OQS_KEM* kem = OQS_KEM_new(OQS_KEM_alg_ml_kem_768);
    if (!kem) {
        LogPrintf("Kyber::Decaps: OQS_KEM_new(ML-KEM-768) failed\n");
        return false;
    }

    OQS_STATUS rc = OQS_KEM_decaps(kem, ss, ct, sk);
    OQS_KEM_free(kem);

    if (rc != OQS_SUCCESS) {
        LogPrintf("Kyber::Decaps: OQS_KEM_decaps failed\n");
        return false;
    }

    return true;
}

} // namespace pqc
