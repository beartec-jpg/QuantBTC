#ifndef BITCOIN_CRYPTO_PQC_KYBER_H
#define BITCOIN_CRYPTO_PQC_KYBER_H

#include <stdint.h>
#include <stdlib.h>

#include <oqs/oqs.h>

// ML-KEM-768 parameters (NIST FIPS 203, formerly CRYSTALS-Kyber)
#define KYBER_N 256
#endif
#ifndef KYBER_K
#define KYBER_K 3
#endif
#ifndef KYBER_Q
#define KYBER_Q 3329
#define KYBER_PUBLIC_KEY_BYTES   OQS_KEM_ml_kem_768_length_public_key     // 1184
#define KYBER_SECRET_KEY_BYTES   OQS_KEM_ml_kem_768_length_secret_key     // 2400
#define KYBER_CIPHERTEXT_BYTES   OQS_KEM_ml_kem_768_length_ciphertext     // 1088
#define KYBER_SHARED_SECRET_BYTES OQS_KEM_ml_kem_768_length_shared_secret // 32

namespace pqc {

/**
 * ML-KEM-768 Key Encapsulation Mechanism.
 *
 * Wraps liboqs OQS_KEM implementation of NIST FIPS 203 (ML-KEM-768).
 * Security level: NIST Level 3 (roughly equivalent to AES-192).
 */
class Kyber {
public:
    static bool KeyGen(unsigned char *pk, unsigned char *sk);
    static bool Encaps(unsigned char *ct, unsigned char *ss, const unsigned char *pk);
    static bool Decaps(unsigned char *ss, const unsigned char *ct, const unsigned char *sk);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_KYBER_H
