#ifndef FALCON_RANDOMBYTES_H
#define FALCON_RANDOMBYTES_H
/* Bridges PQClean randombytes() API to Bitcoin Core's GetStrongRandBytes().
 * The implementation lives in src/crypto/pqc/ml-dsa/randombytes.cpp and is
 * shared across all vendored PQC libraries (ml-dsa, ml-kem, sphincsplus, falcon-padded). */
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void randombytes(uint8_t *out, size_t outlen);
#ifdef __cplusplus
}
#endif
#endif /* FALCON_RANDOMBYTES_H */
