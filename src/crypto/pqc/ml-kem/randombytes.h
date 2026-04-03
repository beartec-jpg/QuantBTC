#ifndef RANDOMBYTES_H
#define RANDOMBYTES_H

#include <stddef.h>
#include <stdint.h>

/* Implemented in randombytes.cpp using Bitcoin Core's GetStrongRandBytes */
void randombytes(uint8_t *out, size_t outlen);

#endif
