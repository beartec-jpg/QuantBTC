#ifndef BITCOIN_CRYPTO_PQC_FRODOKEM_H
#define BITCOIN_CRYPTO_PQC_FRODOKEM_H

#include <stdint.h>
#include <stdlib.h>

// FrodoKEM-976 parameters (NIST Level 3)
#define FRODO_N 976
#define FRODO_Q 65536
#define FRODO_PUBLIC_KEY_BYTES 15632
#define FRODO_SECRET_KEY_BYTES 31296
#define FRODO_CIPHERTEXT_BYTES 15744
#define FRODO_SHARED_SECRET_BYTES 24

namespace pqc {

class FrodoKEM {
public:
    // Key generation
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    
    // Encapsulation
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    
    // Decapsulation
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);

private:
    // Internal helper functions
    static void SampleMatrix(uint16_t *a, const unsigned char *seed);
    static void MatrixMultiply(uint16_t *c, const uint16_t *a, const uint16_t *b, size_t n);
    static void AddRoundq(uint16_t *out, const uint16_t *a, const uint16_t *b, size_t n);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_FRODOKEM_H
