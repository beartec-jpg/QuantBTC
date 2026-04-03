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

/**
 * Compute the inverse of polynomial 'in' modulo (X^N - 1) over Z/qZ
 * using the "almost inverse" algorithm (based on NTRU standard).
 *
 * First computes the inverse modulo 2 (binary), then lifts it to
 * modulo q = 4096 via Newton iteration.
 *
 * Returns true on success, false if the polynomial is not invertible.
 */
static bool poly_invert(int16_t *out, const int16_t *in) {
    // Step 1: Compute inverse mod 2 using the "almost inverse" algorithm
    // in the ring Z_2[X]/(X^N - 1)
    int16_t b[NTRU_N] = {0};
    int16_t c[NTRU_N] = {0};
    int16_t f[NTRU_N];
    int16_t g[NTRU_N] = {0};

    // f = input polynomial mod 2
    for (int i = 0; i < NTRU_N; i++) {
        f[i] = ((in[i] % 2) + 2) % 2;
    }

    // g = X^N - 1 mod 2 = X^N + 1 mod 2
    g[0] = 1;
    g[NTRU_N - 1] = 1;  // x^(N-1) + 1 represents X^N - 1 after reduction

    b[0] = 1;
    // c is already zero

    int deg_f = NTRU_N - 1;
    while (deg_f >= 0 && f[deg_f] == 0) deg_f--;
    int deg_g = NTRU_N - 1;
    while (deg_g >= 0 && g[deg_g] == 0) deg_g--;

    // Almost inverse mod 2
    int k = 0;
    const int max_iter = 2 * NTRU_N * NTRU_N;  // generous upper bound
    for (int iter = 0; iter < max_iter; iter++) {
        // Find lowest set coefficient of f
        while (deg_f >= 0 && f[0] == 0) {
            // f = f / x  (shift right)
            for (int i = 0; i < NTRU_N - 1; i++) f[i] = f[i + 1];
            f[NTRU_N - 1] = 0;
            // c = c * x  (shift left, with wraparound mod X^N - 1)
            int16_t last = c[NTRU_N - 1];
            for (int i = NTRU_N - 1; i > 0; i--) c[i] = c[i - 1];
            c[0] = last;
            k++;
            deg_f--;
        }
        if (deg_f < 0) {
            // f is zero — input is not invertible mod 2
            return false;
        }
        if (deg_f == 0) {
            // f = 1 (constant) — we have the inverse mod 2
            break;
        }
        if (deg_f < deg_g) {
            // swap f <-> g, b <-> c
            for (int i = 0; i < NTRU_N; i++) { int16_t t = f[i]; f[i] = g[i]; g[i] = t; }
            for (int i = 0; i < NTRU_N; i++) { int16_t t = b[i]; b[i] = c[i]; c[i] = t; }
            int tmp = deg_f; deg_f = deg_g; deg_g = tmp;
        }
        // f = f + g mod 2,  b = b + c mod 2
        for (int i = 0; i < NTRU_N; i++) {
            f[i] = (f[i] + g[i]) & 1;
            b[i] = (b[i] + c[i]) & 1;
        }
        while (deg_f >= 0 && f[deg_f] == 0) deg_f--;
    }

    if (deg_f != 0) {
        // Failed to converge — input is not invertible
        return false;
    }

    // b now holds the inverse mod 2.  Adjust for the x^k rotation.
    // Rotate b by (N - k) positions mod N to undo the k shifts.
    {
        int16_t tmp[NTRU_N];
        int shift = ((k % NTRU_N) + NTRU_N) % NTRU_N;
        for (int i = 0; i < NTRU_N; i++) {
            tmp[(i + shift) % NTRU_N] = b[i];
        }
        memcpy(b, tmp, sizeof(tmp));
    }

    // Step 2: Lift from mod 2 to mod q = 4096 via Newton iteration.
    // b holds inverse mod 2.  Newton: b_{i+1} = b_i * (2 - in * b_i) mod q
    // log2(4096) = 12, so we need iterations for mod 4, 8, 16, ..., 4096
    // That's 11 doublings (2 -> 4 -> 8 -> 16 -> 32 -> 64 -> 128 -> 256 -> 512 -> 1024 -> 2048 -> 4096)
    for (int round = 0; round < 11; round++) {
        int16_t temp[NTRU_N];
        int16_t prod[NTRU_N];

        // prod = in * b mod (X^N - 1)
        poly_mul(prod, in, b);

        // temp = 2 - prod
        for (int i = 0; i < NTRU_N; i++) {
            temp[i] = (-prod[i]) % NTRU_Q;
            if (temp[i] < 0) temp[i] += NTRU_Q;
        }
        temp[0] = (2 - prod[0] % NTRU_Q + NTRU_Q) % NTRU_Q;

        // b = b * temp mod (X^N - 1)
        poly_mul(b, b, temp);

        // Reduce mod q
        for (int i = 0; i < NTRU_N; i++) {
            b[i] = ((b[i] % NTRU_Q) + NTRU_Q) % NTRU_Q;
        }
    }

    memcpy(out, b, NTRU_N * sizeof(int16_t));
    return true;
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
    if (!poly_invert(f_inv, f)) {
        // f is not invertible; retry key generation would be needed in practice.
        return false;
    }
    
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
    FastRandomContext rng;
    
    // Generate random message
    GetStrongRandBytes(m);
    
    // Unpack public key
    memcpy(h, pk, NTRU_N * sizeof(int16_t));
    
    // Generate small polynomial r
    for(int i = 0; i < NTRU_N; i++) {
        r[i] = (static_cast<int16_t>(rng.randrange(3)) - 1) % NTRU_Q;
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
