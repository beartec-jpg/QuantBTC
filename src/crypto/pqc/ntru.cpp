#include "ntru.h"
#include "../common.h"
#include "../sha256.h"
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
    int16_t aux[NTRU_N];
    
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

bool NTRU::KeyGen(unsigned char *pk, unsigned char *sk) {
    int16_t f[NTRU_N];
    int16_t g[NTRU_N];
    int16_t h[NTRU_N];
    
    // Generate small polynomial f
    for(int i = 0; i < NTRU_N; i++) {
        f[i] = (GetRand(3) - 1) % NTRU_Q;
        if(f[i] < 0) f[i] += NTRU_Q;
    }
    
    // Generate small polynomial g
    for(int i = 0; i < NTRU_N; i++) {
        g[i] = (GetRand(3) - 1) % NTRU_Q;
        if(g[i] < 0) g[i] += NTRU_Q;
    }
    
    // Compute f^-1
    int16_t f_inv[NTRU_N];
    poly_invert(f_inv, f);
    
    // Compute h = g * f^-1
    poly_mul(h, g, f_inv);
    
    // Pack public and private keys
    memcpy(pk, h, NTRU_N * sizeof(int16_t));
    memcpy(sk, f, NTRU_N * sizeof(int16_t));
    memcpy(sk + NTRU_N * sizeof(int16_t), g, NTRU_N * sizeof(int16_t));
    
    return true;
}

bool NTRU::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    int16_t r[NTRU_N];
    int16_t h[NTRU_N];
    unsigned char m[32];
    
    // Generate random message
    GetStrongRandBytes(m, 32);
    
    // Unpack public key
    memcpy(h, pk, NTRU_N * sizeof(int16_t));
    
    // Generate small polynomial r
    for(int i = 0; i < NTRU_N; i++) {
        r[i] = (GetRand(3) - 1) % NTRU_Q;
        if(r[i] < 0) r[i] += NTRU_Q;
    }
    
    // Compute e = r * h
    int16_t e[NTRU_N];
    poly_mul(e, r, h);
    
    // Add message encoding
    for(int i = 0; i < NTRU_N; i++) {
        e[i] = (e[i] + ((m[i/8] >> (i%8)) & 1) * (NTRU_Q/2)) % NTRU_Q;
    }
    
    // Pack ciphertext
    memcpy(ct, e, NTRU_N * sizeof(int16_t));
    
    // Generate shared secret
    CSHA256().Write(m, 32).Finalize(ss);
    
    return true;
}

bool NTRU::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    int16_t e[NTRU_N];
    int16_t f[NTRU_N];
    int16_t g[NTRU_N];
    
    // Unpack ciphertext and secret key
    memcpy(e, ct, NTRU_N * sizeof(int16_t));
    memcpy(f, sk, NTRU_N * sizeof(int16_t));
    memcpy(g, sk + NTRU_N * sizeof(int16_t), NTRU_N * sizeof(int16_t));
    
    // Compute f * e
    int16_t fe[NTRU_N];
    poly_mul(fe, f, e);
    
    // Recover message
    unsigned char m[32] = {0};
    for(int i = 0; i < NTRU_N; i++) {
        if(fe[i] > NTRU_Q/2) {
            m[i/8] |= 1 << (i%8);
        }
    }
    
    // Generate shared secret
    CSHA256().Write(m, 32).Finalize(ss);
    
    return true;
}

} // namespace pqc
