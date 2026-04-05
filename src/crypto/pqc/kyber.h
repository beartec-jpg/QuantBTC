#ifndef BITCOIN_CRYPTO_PQC_KYBER_H
#define BITCOIN_CRYPTO_PQC_KYBER_H

#include <stdint.h>
#include <stdlib.h>

// ML-KEM-768 parameters (NIST FIPS 203, formerly CRYSTALS-Kyber)
#define KYBER_N 256
#endif
#ifndef KYBER_K
#define KYBER_K 3
#endif
#ifndef KYBER_Q
#define KYBER_Q 3329
#define KYBER_PUBLIC_KEY_BYTES   1184  // ML-KEM-768 public key
#define KYBER_SECRET_KEY_BYTES   2400  // ML-KEM-768 secret key
#define KYBER_CIPHERTEXT_BYTES   1088  // ML-KEM-768 ciphertext
#define KYBER_SHARED_SECRET_BYTES 32   // ML-KEM-768 shared secret

namespace pqc {

/**
 * ML-KEM-768 Key Encapsulation Mechanism — STUB.
 *
 * All operations return false until a vendored implementation is added.
 * The liboqs dependency has been removed.
 */
class Kyber {
public:
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_KYBER_H
