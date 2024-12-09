#include "frodokem.h"
#include "../common.h"
#include "../sha256.h"
#include "../random.h"
#include <string.h>

namespace pqc {

// FrodoKEM-976 parameters
#define FRODO_N 976
#define FRODO_NBAR 8
#define FRODO_MBAR 8
#define FRODO_B 2
#define FRODO_LOGQ 16

static void pack(unsigned char *out, const uint16_t *in, size_t len) {
    for(size_t i = 0; i < len; i++) {
        out[2*i] = in[i] & 0xff;
        out[2*i + 1] = (in[i] >> 8) & 0xff;
    }
}

static void unpack(uint16_t *out, const unsigned char *in, size_t len) {
    for(size_t i = 0; i < len; i++) {
        out[i] = ((uint16_t)in[2*i]) | (((uint16_t)in[2*i + 1]) << 8);
    }
}

static void sample_error(uint16_t *e, size_t n) {
    for(size_t i = 0; i < n; i++) {
        // Sample from discrete Gaussian distribution
        int32_t sum = 0;
        for(int j = 0; j < 16; j++) {
            sum += (int32_t)GetRand(2) - 1;
        }
        e[i] = (uint16_t)((sum + FRODO_Q) % FRODO_Q);
    }
}

bool FrodoKEM::KeyGen(unsigned char *pk, unsigned char *sk) {
    uint16_t A[FRODO_N * FRODO_N];
    uint16_t S[FRODO_N * FRODO_NBAR];
    uint16_t E[FRODO_N * FRODO_NBAR];
    uint16_t B[FRODO_N * FRODO_NBAR];
    unsigned char seed[32];
    
    // Generate random seed for matrix A
    GetStrongRandBytes(seed, 32);
    
    // Generate matrix A pseudorandomly
    CSHA256 sha256;
    for(size_t i = 0; i < FRODO_N; i++) {
        for(size_t j = 0; j < FRODO_N; j++) {
            unsigned char tmp[32];
            sha256.Reset();
            sha256.Write(seed, 32);
            sha256.Write((unsigned char*)&i, sizeof(i));
            sha256.Write((unsigned char*)&j, sizeof(j));
            sha256.Finalize(tmp);
            A[i * FRODO_N + j] = (*(uint16_t*)tmp) % FRODO_Q;
        }
    }
    
    // Sample error matrices S and E
    sample_error(S, FRODO_N * FRODO_NBAR);
    sample_error(E, FRODO_N * FRODO_NBAR);
    
    // Compute B = AS + E
    for(size_t i = 0; i < FRODO_N; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k = 0; k < FRODO_N; k++) {
                sum += (uint32_t)A[i * FRODO_N + k] * S[k * FRODO_NBAR + j];
            }
            B[i * FRODO_NBAR + j] = (sum + E[i * FRODO_NBAR + j]) % FRODO_Q;
        }
    }
    
    // Pack public key (seed || B)
    memcpy(pk, seed, 32);
    pack(pk + 32, B, FRODO_N * FRODO_NBAR);
    
    // Pack secret key (S || pk)
    pack(sk, S, FRODO_N * FRODO_NBAR);
    memcpy(sk + 2 * FRODO_N * FRODO_NBAR, pk, FRODO_PUBLIC_KEY_BYTES);
    
    return true;
}

bool FrodoKEM::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    uint16_t Sp[FRODO_MBAR * FRODO_N];
    uint16_t Ep[FRODO_MBAR * FRODO_N];
    uint16_t Epp[FRODO_MBAR * FRODO_NBAR];
    uint16_t V[FRODO_MBAR * FRODO_NBAR];
    unsigned char mu[32];
    
    // Generate random mu
    GetStrongRandBytes(mu, 32);
    
    // Sample error matrices
    sample_error(Sp, FRODO_MBAR * FRODO_N);
    sample_error(Ep, FRODO_MBAR * FRODO_N);
    sample_error(Epp, FRODO_MBAR * FRODO_NBAR);
    
    // Reconstruct A from seed
    uint16_t A[FRODO_N * FRODO_N];
    const unsigned char *seed = pk;
    CSHA256 sha256;
    for(size_t i = 0; i < FRODO_N; i++) {
        for(size_t j = 0; j < FRODO_N; j++) {
            unsigned char tmp[32];
            sha256.Reset();
            sha256.Write(seed, 32);
            sha256.Write((unsigned char*)&i, sizeof(i));
            sha256.Write((unsigned char*)&j, sizeof(j));
            sha256.Finalize(tmp);
            A[i * FRODO_N + j] = (*(uint16_t*)tmp) % FRODO_Q;
        }
    }
    
    // Unpack B from public key
    uint16_t B[FRODO_N * FRODO_NBAR];
    unpack(B, pk + 32, FRODO_N * FRODO_NBAR);
    
    // Compute V = SpB + Epp
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k = 0; k < FRODO_N; k++) {
                sum += (uint32_t)Sp[i * FRODO_N + k] * B[k * FRODO_NBAR + j];
            }
            V[i * FRODO_NBAR + j] = (sum + Epp[i * FRODO_NBAR + j]) % FRODO_Q;
        }
    }
    
    // Encode mu into V
    for(size_t i = 0; i < FRODO_MBAR * FRODO_NBAR; i++) {
        V[i] = (V[i] + (((mu[i/8] >> (i%8)) & 1) << (FRODO_LOGQ-1))) % FRODO_Q;
    }
    
    // Pack ciphertext (C1 || C2)
    pack(ct, Sp, FRODO_MBAR * FRODO_N);
    pack(ct + 2 * FRODO_MBAR * FRODO_N, V, FRODO_MBAR * FRODO_NBAR);
    
    // Generate shared secret
    CSHA256().Write(mu, 32).Finalize(ss);
    
    return true;
}

bool FrodoKEM::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    uint16_t C1[FRODO_MBAR * FRODO_N];
    uint16_t C2[FRODO_MBAR * FRODO_NBAR];
    uint16_t S[FRODO_N * FRODO_NBAR];
    
    // Unpack ciphertext and secret key
    unpack(C1, ct, FRODO_MBAR * FRODO_N);
    unpack(C2, ct + 2 * FRODO_MBAR * FRODO_N, FRODO_MBAR * FRODO_NBAR);
    unpack(S, sk, FRODO_N * FRODO_NBAR);
    
    // Compute C1S
    uint16_t W[FRODO_MBAR * FRODO_NBAR];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k = 0; k < FRODO_N; k++) {
                sum += (uint32_t)C1[i * FRODO_N + k] * S[k * FRODO_NBAR + j];
            }
            W[i * FRODO_NBAR + j] = sum % FRODO_Q;
        }
    }
    
    // Recover mu
    unsigned char mu[32] = {0};
    for(size_t i = 0; i < FRODO_MBAR * FRODO_NBAR; i++) {
        uint16_t diff = (C2[i] - W[i] + FRODO_Q) % FRODO_Q;
        if(diff > FRODO_Q/2) {
            mu[i/8] |= 1 << (i%8);
        }
    }
    
    // Generate shared secret
    CSHA256().Write(mu, 32).Finalize(ss);
    
    return true;
}

} // namespace pqc
