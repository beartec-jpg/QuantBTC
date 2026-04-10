/* Standalone randombytes for security testing tools — uses OpenSSL RAND_bytes */
#include "randombytes.h"
#include <openssl/rand.h>

void randombytes(uint8_t *out, size_t outlen) {
    RAND_bytes(out, (int)outlen);
}
