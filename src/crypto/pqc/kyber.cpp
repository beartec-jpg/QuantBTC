#include "kyber.h"
#include "../common.h"
#include "../sha256.h"
#include "../random.h"
#include <string.h>

namespace pqc {

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
}

bool Kyber::KeyGen(unsigned char *pk, unsigned char *sk) {
    int16_t a[KYBER_N];
    int16_t e[KYBER_N];
    int16_t s[KYBER_N];
    unsigned char seed[32];
    unsigned char nonce = 0;
    
    // Generate random seed
    GetStrongRandBytes(seed, 32);
    
    // Generate polynomial a from seed
    GeneratePolynomial(a, seed);
    
    // Sample secret polynomial s
    for(int i = 0; i < KYBER_N; i++) {
        s[i] = (GetRand(5) - 2) % KYBER_Q;
        if(s[i] < 0) s[i] += KYBER_Q;
    }
    
    // Sample error polynomial e
    for(int i = 0; i < KYBER_N; i++) {
        e[i] = (GetRand(5) - 2) % KYBER_Q;
        if(e[i] < 0) e[i] += KYBER_Q;
    }
    
    // Transform to NTT domain
    ntt(a);
    ntt(s);
    ntt(e);
    
    // Compute public key b = as + e
    int16_t b[KYBER_N];
    for(int i = 0; i < KYBER_N; i++) {
        b[i] = (((int32_t)a[i] * s[i]) % KYBER_Q + e[i]) % KYBER_Q;
    }
    
    // Pack public and private keys
    memcpy(pk, seed, 32);
    memcpy(pk + 32, b, KYBER_N * sizeof(int16_t));
    memcpy(sk, s, KYBER_N * sizeof(int16_t));
    memcpy(sk + KYBER_N * sizeof(int16_t), pk, KYBER_PUBLIC_KEY_BYTES);
    
    return true;
}

void Kyber::GeneratePolynomial(int16_t *a, const unsigned char *seed) {
    // Use SHA256 to expand seed into polynomial coefficients
    CSHA256 sha256;
    unsigned char output[KYBER_N * 2];
    
    sha256.Write(seed, 32);
    sha256.Finalize(output);
    
    for(int i = 0; i < KYBER_N; i++) {
        uint16_t val = (output[2*i] << 8) | output[2*i + 1];
        a[i] = val % KYBER_Q;
    }
}

bool Kyber::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    int16_t r[KYBER_N];
    int16_t e1[KYBER_N];
    int16_t e2[KYBER_N];
    unsigned char m[32];
    
    // Generate random message
    GetStrongRandBytes(m, 32);
    
    // Sample r from centered binomial distribution
    for(int i = 0; i < KYBER_N; i++) {
        r[i] = (GetRand(5) - 2) % KYBER_Q;
        if(r[i] < 0) r[i] += KYBER_Q;
    }
    
    // Sample error terms
    for(int i = 0; i < KYBER_N; i++) {
        e1[i] = (GetRand(5) - 2) % KYBER_Q;
        e2[i] = (GetRand(5) - 2) % KYBER_Q;
        if(e1[i] < 0) e1[i] += KYBER_Q;
        if(e2[i] < 0) e2[i] += KYBER_Q;
    }
    
    // Transform to NTT domain
    ntt(r);
    
    // Compute u = a'r + e1
    int16_t u[KYBER_N];
    const int16_t *a = (const int16_t *)(pk + 32);
    for(int i = 0; i < KYBER_N; i++) {
        u[i] = (((int32_t)a[i] * r[i]) % KYBER_Q + e1[i]) % KYBER_Q;
    }
    
    // Compute v = b'r + e2 + encode(m)
    int16_t v[KYBER_N];
    const int16_t *b = (const int16_t *)(pk + 32 + KYBER_N * sizeof(int16_t));
    for(int i = 0; i < KYBER_N; i++) {
        v[i] = (((int32_t)b[i] * r[i]) % KYBER_Q + e2[i]) % KYBER_Q;
        // Add encoded message
        v[i] = (v[i] + ((m[i/8] >> (i%8)) & 1) * (KYBER_Q/2)) % KYBER_Q;
    }
    
    // Pack ciphertext
    memcpy(ct, u, KYBER_N * sizeof(int16_t));
    memcpy(ct + KYBER_N * sizeof(int16_t), v, KYBER_N * sizeof(int16_t));
    
    // Generate shared secret
    CSHA256 sha256;
    sha256.Write(m, 32);
    sha256.Finalize(ss);
    
    return true;
}

bool Kyber::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    int16_t m[KYBER_N];
    const int16_t *u = (const int16_t *)ct;
    const int16_t *v = (const int16_t *)(ct + KYBER_N * sizeof(int16_t));
    const int16_t *s = (const int16_t *)sk;
    
    // Compute v - us
    for(int i = 0; i < KYBER_N; i++) {
        m[i] = (v[i] - ((int32_t)u[i] * s[i]) % KYBER_Q) % KYBER_Q;
        if(m[i] < 0) m[i] += KYBER_Q;
        // Decode message
        m[i] = (2 * m[i] + KYBER_Q/2) / KYBER_Q;
    }
    
    // Pack decoded message
    unsigned char decoded_m[32] = {0};
    for(int i = 0; i < KYBER_N; i++) {
        decoded_m[i/8] |= (m[i] & 1) << (i%8);
    }
    
    // Generate shared secret
    CSHA256 sha256;
    sha256.Write(decoded_m, 32);
    sha256.Finalize(ss);
    
    return true;
}

} // namespace pqc
