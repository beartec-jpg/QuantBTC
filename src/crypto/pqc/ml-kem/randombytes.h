#ifndef BITCOIN_CRYPTO_PQC_ML_KEM_RANDOMBYTES_H
#define BITCOIN_CRYPTO_PQC_ML_KEM_RANDOMBYTES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Implemented in ml-dsa/randombytes.cpp using Bitcoin Core's GetStrongRandBytes */
void randombytes(uint8_t *out, size_t outlen);

#ifdef __cplusplus
} // extern "C"
#endif

#endif
