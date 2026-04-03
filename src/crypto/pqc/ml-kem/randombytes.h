#ifndef BITCOIN_CRYPTO_PQC_ML_KEM_RANDOMBYTES_H
#define BITCOIN_CRYPTO_PQC_ML_KEM_RANDOMBYTES_H

#include <stddef.h>
#include <stdint.h>

/* Implemented in randombytes.cpp using Bitcoin Core's GetStrongRandBytes */
void randombytes(uint8_t *out, size_t outlen);

#endif
