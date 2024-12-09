#ifndef BITCOIN_CRYPTO_PQC_KYBER_H
#define BITCOIN_CRYPTO_PQC_KYBER_H

#include <stdint.h>
#include <stdlib.h>

// Kyber-768 parameters
#define KYBER_N 256
#define KYBER_K 3
#define KYBER_Q 3329
#define KYBER_PUBLIC_KEY_BYTES 1184
#define KYBER_SECRET_KEY_BYTES 2400
#define KYBER_CIPHERTEXT_BYTES 1088
#define KYBER_SHARED_SECRET_BYTES 32

namespace pqc {

class Kyber {
public:
    // Key generation
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    
    // Encapsulation
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    
    // Decapsulation
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);

private:
    // Internal helper functions
    static void GeneratePolynomial(int16_t *a, const unsigned char *seed);
    static void NTT(int16_t *poly);
    static void InverseNTT(int16_t *poly);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_KYBER_H
