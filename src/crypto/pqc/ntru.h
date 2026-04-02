#ifndef BITCOIN_CRYPTO_PQC_NTRU_H
#define BITCOIN_CRYPTO_PQC_NTRU_H

#include <stdint.h>
#include <stdlib.h>

// NTRU-HPS-4096-821 parameters (retained for API compatibility)
// NOTE: NTRU was NOT selected by NIST for standardization.
// All operations return false. Use ML-KEM-768 (Kyber) instead.
#define NTRU_N 821
#define NTRU_Q 4096
#define NTRU_PUBLIC_KEY_BYTES 1642
#define NTRU_SECRET_KEY_BYTES 3284
#define NTRU_CIPHERTEXT_BYTES 1642
#define NTRU_SHARED_SECRET_BYTES 32

namespace pqc {

class NTRU {
public:
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_NTRU_H
