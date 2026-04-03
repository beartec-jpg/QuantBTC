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
#include <support/cleanse.h>

/* Pull in the Kyber-768 reference implementation as C */
extern "C" {
#include "ml-kem/params.h"
#include "ml-kem/kem.h"
}

static_assert(KYBER_PUBLIC_KEY_BYTES  == KYBER_PUBLICKEYBYTES,
              "Kyber PUBLIC_KEY_BYTES mismatch with reference params");
static_assert(KYBER_SECRET_KEY_BYTES  == KYBER_SECRETKEYBYTES,
              "Kyber SECRET_KEY_BYTES mismatch with reference params");
static_assert(KYBER_CIPHERTEXT_BYTES  == KYBER_CIPHERTEXTBYTES,
              "Kyber CIPHERTEXT_BYTES mismatch with reference params");
static_assert(KYBER_SHARED_SECRET_BYTES == KYBER_SSBYTES,
              "Kyber SHARED_SECRET_BYTES mismatch with reference params");

namespace pqc {

bool Kyber::KeyGen(unsigned char *pk, unsigned char *sk)
{
    int ret = crypto_kem_keypair(pk, sk);
    if (ret != 0) {
        LogPrintf("Kyber::KeyGen: crypto_kem_keypair failed (%d)\n", ret);
        memory_cleanse(pk, KYBER_PUBLICKEYBYTES);
        memory_cleanse(sk, KYBER_SECRETKEYBYTES);
        return false;
    }
    return true;
}

bool Kyber::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk)
{
    int ret = crypto_kem_enc(ct, ss, pk);
    if (ret != 0) {
        LogPrintf("Kyber::Encaps: crypto_kem_enc failed (%d)\n", ret);
        memory_cleanse(ct, KYBER_CIPHERTEXTBYTES);
        memory_cleanse(ss, KYBER_SSBYTES);
        return false;
    }
    return true;
}

bool Kyber::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk)
{
    int ret = crypto_kem_dec(ss, ct, sk);
    if (ret != 0) {
        LogPrintf("Kyber::Decaps: crypto_kem_dec failed (%d)\n", ret);
        memory_cleanse(ss, KYBER_SSBYTES);
        return false;
    }
    return true;
}

} // namespace pqc
