#include "ntru.h"
#include "pqc_fo_utils.h"
#include "../common.h"
#include "../sha256.h"
#include "../sha512.h"
#include "../random.h"
#include <string.h>

namespace pqc {

// NTRU parameters for n = 821, q = 4096
#define NTRU_N 821
#define NTRU_Q 4096
#define NTRU_P 3

static void poly_mul(int16_t *c, const int16_t *a, const int16_t *b) {
    int32_t temp[2 * NTRU_N] = {0};
    
    // Schoolbook multiplication
    for(int i = 0; i < NTRU_N; i++) {
        for(int j = 0; j < NTRU_N; j++) {
            temp[i + j] = (temp[i + j] + (int32_t)a[i] * b[j]) % NTRU_Q;
        }
    }
    
    // Reduce modulo X^n - 1
    for(int i = NTRU_N; i < 2 * NTRU_N; i++) {
        temp[i - NTRU_N] = (temp[i - NTRU_N] + temp[i]) % NTRU_Q;
    }
    
    // Copy result
    for(int i = 0; i < NTRU_N; i++) {
        c[i] = (int16_t)temp[i];
    }
}

static void poly_invert(int16_t *out, const int16_t *in) {
    // Extended Euclidean algorithm in polynomial ring
    int16_t v[NTRU_N] = {0};
    int16_t r[NTRU_N];
    int16_t aux[NTRU_N] = {0};
    
    // Initialize
    memcpy(r, in, NTRU_N * sizeof(int16_t));
    v[0] = 1;
    
    // Main loop
    for(int i = 0; i < 100; i++) {  // Maximum iterations
        int16_t quotient = r[NTRU_N-1] / NTRU_P;
        
        // r = r - q * p
        for(int j = 0; j < NTRU_N; j++) {
            r[j] = (r[j] - quotient * NTRU_P) % NTRU_Q;
            if(r[j] < 0) r[j] += NTRU_Q;
        }
        
        // v = v - q * aux
        for(int j = 0; j < NTRU_N; j++) {
            v[j] = (v[j] - quotient * aux[j]) % NTRU_Q;
            if(v[j] < 0) v[j] += NTRU_Q;
        }
        
        // Check if done
        bool done = true;
        for(int j = 0; j < NTRU_N; j++) {
            if(r[j] != 0) {
                done = false;
                break;
            }
        }
        if(done) break;
        
        // Swap r and aux, v and out
        memcpy(aux, r, NTRU_N * sizeof(int16_t));
        memcpy(r, out, NTRU_N * sizeof(int16_t));
        memcpy(out, v, NTRU_N * sizeof(int16_t));
        memcpy(v, aux, NTRU_N * sizeof(int16_t));
    }
}

/**
 * Deterministically sample a trinary polynomial from a 32-byte seed.
 * Coefficients are in {0, NTRU_Q-1, 1} representing {0, -1, 1} mod NTRU_Q.
 * Uses SHA-256 in counter mode to expand the seed.
 */
static void sample_poly_deterministic(int16_t *r, const unsigned char *seed)
{
    // Each SHA-256 block produces 32 bytes; iterate until all NTRU_N coefficients are filled
    for (int block = 0; block * 32 < NTRU_N; block++) {
        unsigned char counter[4];
        counter[0] = (unsigned char)(block & 0xff);
        counter[1] = (unsigned char)((block >> 8) & 0xff);
        counter[2] = 0;
        counter[3] = 0;
        unsigned char tmp[32];
        CSHA256().Write(seed, 32).Write(counter, 4).Finalize(tmp);
        for (int i = 0; i < 32 && block * 32 + i < NTRU_N; i++) {
            int idx = block * 32 + i;
            // Map byte mod 3 to {0, -1, 1} then lift to [0, NTRU_Q)
            int16_t val = (int16_t)(tmp[i] % 3) - 1; // {-1, 0, 1}
            r[idx] = (int16_t)((val + NTRU_Q) % NTRU_Q);
        }
    }
}

bool NTRU::KeyGen(unsigned char *pk, unsigned char *sk) {
    int16_t f[NTRU_N];
    int16_t g[NTRU_N];
    int16_t h[NTRU_N];
    FastRandomContext rng;
    
    // Generate small polynomial f
    for(int i = 0; i < NTRU_N; i++) {
        f[i] = (static_cast<int16_t>(rng.randrange(3)) - 1) % NTRU_Q;
        if(f[i] < 0) f[i] += NTRU_Q;
    }
    
    // Generate small polynomial g
    for(int i = 0; i < NTRU_N; i++) {
        g[i] = (static_cast<int16_t>(rng.randrange(3)) - 1) % NTRU_Q;
        if(g[i] < 0) g[i] += NTRU_Q;
    }
    
    // Compute f^-1
    int16_t f_inv[NTRU_N];
    memset(f_inv, 0, sizeof(f_inv));
    poly_invert(f_inv, f);
    
    // Compute h = g * f^-1
    poly_mul(h, g, f_inv);
    
    // Pack public key: h (raw int16_t array, NTRU_N * 2 bytes)
    memcpy(pk, h, NTRU_N * sizeof(int16_t));

    // Pack secret key: f || pk || z
    //   f   : NTRU_N * 2 bytes
    //   pk  : NTRU_PUBLIC_KEY_BYTES bytes (= NTRU_N * 2)
    //   z   : 32 bytes (rejection seed for implicit rejection)
    unsigned char *sk_f  = sk;
    unsigned char *sk_pk = sk + NTRU_N * 2;
    unsigned char *sk_z  = sk + NTRU_N * 2 + NTRU_PUBLIC_KEY_BYTES;

    memcpy(sk_f,  f,  NTRU_N * sizeof(int16_t));
    memcpy(sk_pk, pk, NTRU_PUBLIC_KEY_BYTES);
    GetStrongRandBytes({sk_z, 32});
    
    return true;
}

bool NTRU::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    unsigned char m[32];
    
    // Generate random 32-byte message
    GetStrongRandBytes(m);
    
    // pk_hash = SHA256(pk)
    unsigned char pk_hash[32];
    CSHA256().Write(pk, NTRU_PUBLIC_KEY_BYTES).Finalize(pk_hash);

    // (r_seed || ss_seed) = SHA512(m || H(pk))
    unsigned char sha512_out[64];
    CSHA512().Write(m, 32).Write(pk_hash, 32).Finalize(sha512_out);
    const unsigned char *r_seed  = sha512_out;
    const unsigned char *ss_seed = sha512_out + 32;

    // Unpack public key h
    int16_t h[NTRU_N];
    memcpy(h, pk, NTRU_N * sizeof(int16_t));

    // Sample blinding polynomial r deterministically from r_seed
    int16_t r[NTRU_N];
    sample_poly_deterministic(r, r_seed);
    
    // Compute e = r * h + Encode(m)
    int16_t e[NTRU_N];
    poly_mul(e, r, h);
    for(int i = 0; i < NTRU_N; i++) {
        e[i] = (int16_t)((e[i] + ((m[i/8] >> (i%8)) & 1) * (NTRU_Q/2)) % NTRU_Q);
    }
    
    // Pack ciphertext
    memcpy(ct, e, NTRU_N * sizeof(int16_t));
    
    // Shared secret: ss = SHA256(ss_seed || ct)
    CSHA256().Write(ss_seed, 32).Write(ct, NTRU_CIPHERTEXT_BYTES).Finalize(ss);
    
    return true;
}

bool NTRU::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    // Unpack secret key: f || pk || z
    const unsigned char *sk_f  = sk;
    const unsigned char *sk_pk = sk + NTRU_N * 2;
    const unsigned char *z     = sk + NTRU_N * 2 + NTRU_PUBLIC_KEY_BYTES;

    int16_t f[NTRU_N];
    memcpy(f, sk_f, NTRU_N * sizeof(int16_t));

    int16_t h[NTRU_N];
    memcpy(h, sk_pk, NTRU_N * sizeof(int16_t));

    // Unpack ciphertext
    int16_t e[NTRU_N];
    memcpy(e, ct, NTRU_N * sizeof(int16_t));
    
    // Compute f * e
    int16_t fe[NTRU_N];
    poly_mul(fe, f, e);
    
    // Recover m'
    unsigned char m_prime[32] = {0};
    for(int i = 0; i < NTRU_N; i++) {
        if(fe[i] > NTRU_Q/2) {
            m_prime[i/8] |= (unsigned char)(1 << (i%8));
        }
    }

    // Re-derive (r_seed' || ss_seed') = SHA512(m' || H(pk))
    unsigned char pk_hash[32];
    CSHA256().Write(sk_pk, NTRU_PUBLIC_KEY_BYTES).Finalize(pk_hash);

    unsigned char sha512_out[64];
    CSHA512().Write(m_prime, 32).Write(pk_hash, 32).Finalize(sha512_out);
    const unsigned char *r_seed_prime  = sha512_out;
    const unsigned char *ss_seed_prime = sha512_out + 32;

    // Re-sample r' from r_seed'
    int16_t r_prime[NTRU_N];
    sample_poly_deterministic(r_prime, r_seed_prime);

    // Re-encrypt: e' = r' * h + Encode(m')
    int16_t e_prime[NTRU_N];
    poly_mul(e_prime, r_prime, h);
    for(int i = 0; i < NTRU_N; i++) {
        e_prime[i] = (int16_t)((e_prime[i] + ((m_prime[i/8] >> (i%8)) & 1) * (NTRU_Q/2)) % NTRU_Q);
    }

    // Pack re-encrypted ciphertext
    unsigned char ct_prime[NTRU_CIPHERTEXT_BYTES];
    memcpy(ct_prime, e_prime, NTRU_N * sizeof(int16_t));

    // Constant-time comparison: fail != 0 if ciphertexts differ
    int fail = ct_verify(ct, ct_prime, NTRU_CIPHERTEXT_BYTES);

    // Compute both candidate shared secrets
    unsigned char ss_good[32];
    unsigned char ss_bad[32];
    CSHA256().Write(ss_seed_prime, 32).Write(ct, NTRU_CIPHERTEXT_BYTES).Finalize(ss_good);
    CSHA256().Write(z, 32).Write(ct, NTRU_CIPHERTEXT_BYTES).Finalize(ss_bad);

    // Constant-time selection: use ss_bad (rejection) if fail != 0
    memcpy(ss, ss_good, 32);
    ct_cmov(ss, ss_bad, 32, fail);
    
    return true;
}

} // namespace pqc
