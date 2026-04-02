#ifndef BITCOIN_CRYPTO_PQC_KYBER_H
#define BITCOIN_CRYPTO_PQC_KYBER_H

#include <stdint.h>
#include <stdlib.h>

// Kyber-768 parameters (must agree with ml-kem/params.h)
#ifndef KYBER_N
#define KYBER_N 256
#endif
#ifndef KYBER_K
#define KYBER_K 3
#endif
#ifndef KYBER_Q
#define KYBER_Q 3329
#define KYBER_PUBLIC_KEY_BYTES 544
#define KYBER_SECRET_KEY_BYTES 1056
#define KYBER_CIPHERTEXT_BYTES 1024
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
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_KYBER_H
