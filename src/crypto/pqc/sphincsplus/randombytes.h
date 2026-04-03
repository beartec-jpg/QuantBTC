#ifndef SPX_RANDOMBYTES_H
#define SPX_RANDOMBYTES_H

#include <stddef.h>
#include <stdint.h>

/* Provided by the canonical definition in ml-dsa/randombytes.cpp */
extern void randombytes(uint8_t *x, size_t xlen);

#endif
