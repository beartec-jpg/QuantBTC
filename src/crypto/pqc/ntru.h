#ifndef BITCOIN_CRYPTO_PQC_NTRU_H
#define BITCOIN_CRYPTO_PQC_NTRU_H

#include <stdint.h>
#include <stdlib.h>

// NTRU-HPS-4096-821 parameters
#define NTRU_N 821
#define NTRU_Q 4096
#define NTRU_PUBLIC_KEY_BYTES 1230
#define NTRU_SECRET_KEY_BYTES 1590
#define NTRU_CIPHERTEXT_BYTES 1230
#define NTRU_SHARED_SECRET_BYTES 32

namespace pqc {

class NTRU {
public:
    // Key generation
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    
    // Encapsulation
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    
    // Decapsulation
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);

private:
    // Internal helper functions
    static void PolyMul(int16_t *c, const int16_t *a, const int16_t *b);
    static void PolyInverse(int16_t *out, const int16_t *in);
    static void SampleTrinary(int16_t *f);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_NTRU_H
