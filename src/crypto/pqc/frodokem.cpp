#include "frodokem.h"
#include "pqc_fo_utils.h"
#include "../common.h"
#include "../sha256.h"
#include "../sha512.h"
#include "../random.h"
#include <string.h>
#include <memory>

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
    FastRandomContext rng;
    for(size_t i = 0; i < n; i++) {
        // Sample from discrete Gaussian distribution
        int32_t sum = 0;
        for(int j = 0; j < 16; j++) {
            sum += static_cast<int32_t>(rng.randrange(2)) - 1;
        }
        e[i] = (uint16_t)((sum + FRODO_Q) % FRODO_Q);
    }
}

/**
 * Deterministically sample an error matrix from a 32-byte seed.
 * Uses SHA-256 in counter mode with a domain separation byte.
 * Each output element is a small value lifted into [0, FRODO_Q).
 */
static void sample_error_deterministic(uint16_t *e, size_t n, const unsigned char *seed, unsigned char domain)
{
    // Each SHA-256 call produces 32 bytes → 16 uint16_t samples
    for (size_t block = 0; block * 16 < n; block++) {
        unsigned char counter[4];
        counter[0] = domain;
        counter[1] = (unsigned char)(block & 0xff);
        counter[2] = (unsigned char)((block >> 8) & 0xff);
        counter[3] = 0;
        unsigned char tmp[32];
        CSHA256().Write(seed, 32).Write(counter, 4).Finalize(tmp);
        for (int i = 0; i < 16 && block * 16 + i < n; i++) {
            // Interpret two bytes as a small signed integer in {-2,-1,0,1,2}
            int16_t val = (int16_t)(((uint16_t)tmp[2*i] | ((uint16_t)tmp[2*i+1] << 8)) % 5) - 2;
            e[block * 16 + i] = (uint16_t)((val + FRODO_Q) % FRODO_Q);
        }
    }
}

/**
 * Build the public matrix A from the 32-byte seed stored in pk[0..31].
 * A is allocated on the heap (976×976 uint16_t ≈ 1.86 MB) to avoid
 * stack overflow.
 */
static void build_matrix_A(uint16_t *A, const unsigned char *seed)
{
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
}

bool FrodoKEM::KeyGen(unsigned char *pk, unsigned char *sk) {
    // A is ~1.86 MB — must be on the heap to avoid stack overflow
    std::unique_ptr<uint16_t[]> A(new uint16_t[FRODO_N * FRODO_N]);
    uint16_t S[FRODO_N * FRODO_NBAR];
    uint16_t E[FRODO_N * FRODO_NBAR];
    uint16_t B[FRODO_N * FRODO_NBAR];
    unsigned char seed[32];
    
    // Generate random seed for matrix A
    GetStrongRandBytes(seed);
    
    // Build matrix A from seed
    build_matrix_A(A.get(), seed);
    
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
            B[i * FRODO_NBAR + j] = (uint16_t)((sum + E[i * FRODO_NBAR + j]) % FRODO_Q);
        }
    }
    
    // Pack public key: seed (32 bytes) || Pack(B)
    memcpy(pk, seed, 32);
    pack(pk + 32, B, FRODO_N * FRODO_NBAR);

    // Compute pk_hash = SHA256(pk)
    unsigned char pk_hash[32];
    CSHA256().Write(pk, FRODO_PUBLIC_KEY_BYTES).Finalize(pk_hash);

    // Pack secret key: Pack(S) || pk || s || pk_hash
    unsigned char *sk_S       = sk;
    unsigned char *sk_pk      = sk + 2 * FRODO_N * FRODO_NBAR;
    unsigned char *sk_s       = sk_pk + FRODO_PUBLIC_KEY_BYTES;
    unsigned char *sk_pk_hash = sk_s + 32;

    pack(sk_S, S, FRODO_N * FRODO_NBAR);
    memcpy(sk_pk, pk, FRODO_PUBLIC_KEY_BYTES);
    GetStrongRandBytes({sk_s, 32});
    memcpy(sk_pk_hash, pk_hash, 32);
    
    return true;
}

bool FrodoKEM::Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk) {
    unsigned char mu[32];
    
    // Generate random 32-byte mu
    GetStrongRandBytes(mu);

    // Compute pk_hash = SHA256(pk)
    unsigned char pk_hash[32];
    CSHA256().Write(pk, FRODO_PUBLIC_KEY_BYTES).Finalize(pk_hash);

    // Derive (seed_SE || k) = SHA512(pk_hash || mu)
    unsigned char sha512_out[64];
    CSHA512().Write(pk_hash, 32).Write(mu, 32).Finalize(sha512_out);
    const unsigned char *seed_SE = sha512_out;
    const unsigned char *k       = sha512_out + 32;

    // Derive error seed: r_seed = SHA256(0x96 || seed_SE)
    unsigned char r_seed[32];
    unsigned char domain = 0x96;
    CSHA256().Write(&domain, 1).Write(seed_SE, 32).Finalize(r_seed);

    // Sample Sp, Ep, Epp deterministically from r_seed
    uint16_t Sp[FRODO_MBAR * FRODO_N];
    uint16_t Ep[FRODO_MBAR * FRODO_N];
    uint16_t Epp[FRODO_MBAR * FRODO_NBAR];
    sample_error_deterministic(Sp,  FRODO_MBAR * FRODO_N,    r_seed, 0x01);
    sample_error_deterministic(Ep,  FRODO_MBAR * FRODO_N,    r_seed, 0x02);
    sample_error_deterministic(Epp, FRODO_MBAR * FRODO_NBAR, r_seed, 0x03);

    // A is ~1.86 MB — must be on the heap to avoid stack overflow
    std::unique_ptr<uint16_t[]> A(new uint16_t[FRODO_N * FRODO_N]);
    build_matrix_A(A.get(), pk);

    // Unpack B from public key
    uint16_t B[FRODO_N * FRODO_NBAR];
    unpack(B, pk + 32, FRODO_N * FRODO_NBAR);
    
    // Compute C1 = Sp*A + Ep
    uint16_t C1[FRODO_MBAR * FRODO_N];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_N; j++) {
            uint32_t sum = 0;
            for(size_t k2 = 0; k2 < FRODO_N; k2++) {
                sum += (uint32_t)Sp[i * FRODO_N + k2] * A[k2 * FRODO_N + j];
            }
            C1[i * FRODO_N + j] = (uint16_t)((sum + Ep[i * FRODO_N + j]) % FRODO_Q);
        }
    }

    // Compute C2 = Sp*B + Epp + Encode(mu)
    uint16_t C2[FRODO_MBAR * FRODO_NBAR];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k2 = 0; k2 < FRODO_N; k2++) {
                sum += (uint32_t)Sp[i * FRODO_N + k2] * B[k2 * FRODO_NBAR + j];
            }
            size_t idx = i * FRODO_NBAR + j;
            uint16_t encoded = (uint16_t)(((mu[idx/8] >> (idx%8)) & 1) << (FRODO_LOGQ - 1));
            C2[idx] = (uint16_t)((sum + Epp[idx] + encoded) % FRODO_Q);
        }
    }
    
    // Pack ciphertext: C1 || C2
    pack(ct,                       C1, FRODO_MBAR * FRODO_N);
    pack(ct + 2 * FRODO_MBAR * FRODO_N, C2, FRODO_MBAR * FRODO_NBAR);
    
    // Shared secret: ss = SHA256(ct || k)
    CSHA256().Write(ct, FRODO_CIPHERTEXT_BYTES).Write(k, 32).Finalize(ss);
    
    return true;
}

bool FrodoKEM::Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk) {
    // Unpack secret key: Pack(S) || pk || s || pk_hash
    const unsigned char *sk_S       = sk;
    const unsigned char *sk_pk      = sk + 2 * FRODO_N * FRODO_NBAR;
    const unsigned char *s          = sk_pk + FRODO_PUBLIC_KEY_BYTES;
    const unsigned char *pk_hash    = s + 32;

    uint16_t S[FRODO_N * FRODO_NBAR];
    unpack(S, sk_S, FRODO_N * FRODO_NBAR);

    // Unpack ciphertext: C1 || C2
    uint16_t C1[FRODO_MBAR * FRODO_N];
    uint16_t C2[FRODO_MBAR * FRODO_NBAR];
    unpack(C1, ct,                       FRODO_MBAR * FRODO_N);
    unpack(C2, ct + 2 * FRODO_MBAR * FRODO_N, FRODO_MBAR * FRODO_NBAR);
    
    // Compute W = C1 * S
    uint16_t W[FRODO_MBAR * FRODO_NBAR];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k2 = 0; k2 < FRODO_N; k2++) {
                sum += (uint32_t)C1[i * FRODO_N + k2] * S[k2 * FRODO_NBAR + j];
            }
            W[i * FRODO_NBAR + j] = (uint16_t)(sum % FRODO_Q);
        }
    }
    
    // Recover mu' = Decode(C2 - W)
    unsigned char mu_prime[32] = {0};
    for(size_t i = 0; i < FRODO_MBAR * FRODO_NBAR; i++) {
        uint16_t diff = (uint16_t)((C2[i] - W[i] + FRODO_Q) % FRODO_Q);
        if(diff > FRODO_Q/2) {
            mu_prime[i/8] |= (unsigned char)(1 << (i%8));
        }
    }

    // Re-derive (seed_SE' || k') = SHA512(pk_hash || mu')
    unsigned char sha512_out[64];
    CSHA512().Write(pk_hash, 32).Write(mu_prime, 32).Finalize(sha512_out);
    const unsigned char *seed_SE_prime = sha512_out;
    const unsigned char *k_prime       = sha512_out + 32;

    // Re-derive error seed: r_seed' = SHA256(0x96 || seed_SE')
    unsigned char r_seed_prime[32];
    unsigned char domain = 0x96;
    CSHA256().Write(&domain, 1).Write(seed_SE_prime, 32).Finalize(r_seed_prime);

    // Re-sample Sp', Ep', Epp' from r_seed'
    uint16_t Sp_prime[FRODO_MBAR * FRODO_N];
    uint16_t Ep_prime[FRODO_MBAR * FRODO_N];
    uint16_t Epp_prime[FRODO_MBAR * FRODO_NBAR];
    sample_error_deterministic(Sp_prime,  FRODO_MBAR * FRODO_N,    r_seed_prime, 0x01);
    sample_error_deterministic(Ep_prime,  FRODO_MBAR * FRODO_N,    r_seed_prime, 0x02);
    sample_error_deterministic(Epp_prime, FRODO_MBAR * FRODO_NBAR, r_seed_prime, 0x03);

    // Re-build A from pk stored in sk
    std::unique_ptr<uint16_t[]> A(new uint16_t[FRODO_N * FRODO_N]);
    build_matrix_A(A.get(), sk_pk);

    // Unpack B from pk stored in sk
    uint16_t B[FRODO_N * FRODO_NBAR];
    unpack(B, sk_pk + 32, FRODO_N * FRODO_NBAR);

    // Re-encrypt: C1' = Sp'*A + Ep'
    uint16_t C1_prime[FRODO_MBAR * FRODO_N];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_N; j++) {
            uint32_t sum = 0;
            for(size_t k2 = 0; k2 < FRODO_N; k2++) {
                sum += (uint32_t)Sp_prime[i * FRODO_N + k2] * A[k2 * FRODO_N + j];
            }
            C1_prime[i * FRODO_N + j] = (uint16_t)((sum + Ep_prime[i * FRODO_N + j]) % FRODO_Q);
        }
    }

    // Re-encrypt: C2' = Sp'*B + Epp' + Encode(mu')
    uint16_t C2_prime[FRODO_MBAR * FRODO_NBAR];
    for(size_t i = 0; i < FRODO_MBAR; i++) {
        for(size_t j = 0; j < FRODO_NBAR; j++) {
            uint32_t sum = 0;
            for(size_t k2 = 0; k2 < FRODO_N; k2++) {
                sum += (uint32_t)Sp_prime[i * FRODO_N + k2] * B[k2 * FRODO_NBAR + j];
            }
            size_t idx = i * FRODO_NBAR + j;
            uint16_t encoded = (uint16_t)(((mu_prime[idx/8] >> (idx%8)) & 1) << (FRODO_LOGQ - 1));
            C2_prime[idx] = (uint16_t)((sum + Epp_prime[idx] + encoded) % FRODO_Q);
        }
    }

    // Pack re-encrypted ciphertext
    unsigned char ct_prime[FRODO_CIPHERTEXT_BYTES];
    pack(ct_prime,                           C1_prime, FRODO_MBAR * FRODO_N);
    pack(ct_prime + 2 * FRODO_MBAR * FRODO_N, C2_prime, FRODO_MBAR * FRODO_NBAR);

    // Constant-time comparison: fail != 0 if ciphertexts differ
    int fail = ct_verify(ct, ct_prime, FRODO_CIPHERTEXT_BYTES);

    // Compute both candidate shared secrets
    unsigned char ss_good[32];
    unsigned char ss_bad[32];
    CSHA256().Write(ct, FRODO_CIPHERTEXT_BYTES).Write(k_prime, 32).Finalize(ss_good);
    CSHA256().Write(ct, FRODO_CIPHERTEXT_BYTES).Write(s, 32).Finalize(ss_bad);

    // Constant-time selection: use ss_bad (rejection) if fail != 0
    memcpy(ss, ss_good, 32);
    ct_cmov(ss, ss_bad, 32, fail);

    return true;
}

} // namespace pqc
