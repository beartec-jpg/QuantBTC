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

// NOT PRODUCTION: experimental/test-only Kyber implementation.

// NTT constants for Kyber
static const int16_t zetas[128] = {
    2571, 2970, 1812, 1493, 1422, 287, 202, 3158, 622, 1577, 182, 962,
    2127, 1855, 1468, 573, 2004, 264, 383, 2500, 1458, 1727, 3199, 2648,
    1017, 732, 608, 1787, 411, 3124, 1758, 1223, 652, 2777, 1015, 2036,
    1491, 3047, 1785, 516, 3321, 3089, 2892, 2646, 3682, 2766, 3441, 3451,
    1202, 3675, 1597, 3224, 2554, 2582, 1608, 1100, 2803, 1676, 1146, 2881,
    1750, 2724, 2161, 2054, 1578, 1426, 2405, 2533, 2501, 2562, 1553, 2935,
    1748, 2336, 1663, 1916, 2174, 1823, 1279, 2804, 2177, 2108, 1193, 2396,
    1347, 1167, 1395, 1652, 1825, 1764, 1350, 1912, 1807, 1926, 1547, 2290,
    1409, 1675, 2368, 1889, 1706, 1596, 1327, 1445, 1855, 2134, 1333, 1967,
    1719, 1413, 1745, 2291, 1195, 1086, 1673, 1948, 1813, 1422, 1168, 1498
};

static void ntt(int16_t r[KYBER_N]) {
    unsigned int len, start, j, k;
    int16_t t, zeta;

    k = 1;
    for(len = 128; len >= 2; len >>= 1) {
        for(start = 0; start < KYBER_N; start = j + len) {
            zeta = zetas[k++];
            for(j = start; j < start + len; j++) {
                t = (int16_t)(((int32_t)zeta * r[j + len]) % KYBER_Q);
                r[j + len] = r[j] - t;
                r[j] = r[j] + t;
                if(r[j + len] >= KYBER_Q) r[j + len] -= KYBER_Q;
                if(r[j] >= KYBER_Q) r[j] -= KYBER_Q;
            }
        }
    }
    return true;
}

bool Kyber::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk)
{
    int ret = crypto_kem_enc(ct, ss, pk);
    if (ret != 0) {
        LogPrintf("Kyber::Encaps: crypto_kem_enc failed (%d)\n", ret);
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
