// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_CRYPTO_PQC_FO_UTILS_H
#define BITCOIN_CRYPTO_PQC_FO_UTILS_H

#include <stddef.h>

/**
 * Constant-time primitives for the Fujisaki-Okamoto (FO) transform.
 *
 * These helpers are used by NTRU::Decaps() (ntru.cpp) and
 * FrodoKEM::Decaps() (frodokem.cpp) to implement the full FO
 * transform: each Decaps re-encrypts the recovered plaintext,
 * compares the result against the received ciphertext with
 * ct_verify(), and uses ct_cmov() to select between the real
 * shared secret and a rejection value in constant time.
 * This provides IND-CCA2 security.
 */

/**
 * Constant-time comparison of two byte arrays.
 * Returns 0 if equal, non-zero otherwise.
 * Must not branch on secret data to prevent timing side-channels.
 */
static inline int ct_verify(const unsigned char *a, const unsigned char *b, size_t len)
{
    unsigned char diff = 0;
    for (size_t i = 0; i < len; i++) {
        diff |= a[i] ^ b[i];
    }
    return (int)diff;
}

/**
 * Constant-time conditional move.
 * If condition != 0, copies src to dst.
 * Does not branch on condition or data.
 */
static inline void ct_cmov(unsigned char *dst, const unsigned char *src, size_t len, int condition)
{
    /* Turn condition into an all-ones or all-zeros mask using unsigned
     * arithmetic to avoid implementation-defined signed overflow. */
    unsigned char mask = (unsigned char)(0U - (unsigned int)(condition != 0));
    for (size_t i = 0; i < len; i++) {
        dst[i] = (dst[i] & ~mask) | (src[i] & mask);
    }
}

#endif // BITCOIN_CRYPTO_PQC_FO_UTILS_H
