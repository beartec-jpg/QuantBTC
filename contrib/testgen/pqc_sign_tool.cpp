/* pqc_sign_tool.c — Standalone ML-DSA-44 (Dilithium2) tool for security testing.
 * Uses vendored pq-crystals reference implementation directly.
 *
 * Usage:
 *   ./pqc_sign_tool keygen                    → pk_hex sk_hex
 *   ./pqc_sign_tool sign <sk_hex> <msg_hex>   → sig_hex
 *   ./pqc_sign_tool verify <pk_hex> <sig_hex> <msg_hex> → OK or FAIL
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sign.h"
#include "params.h"

#define PK_BYTES CRYPTO_PUBLICKEYBYTES
#define SK_BYTES CRYPTO_SECRETKEYBYTES
#define SIG_BYTES CRYPTO_BYTES

static int hex2byte(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static size_t hex2bytes(const char *hex, uint8_t *out, size_t max) {
    size_t len = strlen(hex);
    size_t i, n = 0;
    for (i = 0; i + 1 < len && n < max; i += 2) {
        int hi = hex2byte(hex[i]);
        int lo = hex2byte(hex[i+1]);
        if (hi < 0 || lo < 0) break;
        out[n++] = (uint8_t)((hi << 4) | lo);
    }
    return n;
}

static void bytes2hex(const uint8_t *data, size_t len, char *out) {
    size_t i;
    for (i = 0; i < len; i++) {
        sprintf(out + i*2, "%02x", data[i]);
    }
    out[len*2] = '\0';
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s keygen|sign|verify ...\n", argv[0]);
        return 1;
    }

    if (strcmp(argv[1], "keygen") == 0) {
        uint8_t pk[PK_BYTES], sk[SK_BYTES];
        if (crypto_sign_keypair(pk, sk) != 0) {
            fprintf(stderr, "keygen failed\n");
            return 1;
        }
        char *pk_hex = (char*)malloc(PK_BYTES * 2 + 1);
        char *sk_hex = (char*)malloc(SK_BYTES * 2 + 1);
        bytes2hex(pk, PK_BYTES, pk_hex);
        bytes2hex(sk, SK_BYTES, sk_hex);
        printf("%s %s\n", pk_hex, sk_hex);
        free(pk_hex);
        free(sk_hex);
        return 0;
    }

    if (strcmp(argv[1], "sign") == 0 && argc >= 4) {
        uint8_t sk[SK_BYTES];
        hex2bytes(argv[2], sk, SK_BYTES);

        uint8_t msg[4096];
        size_t mlen = hex2bytes(argv[3], msg, sizeof(msg));

        uint8_t sig[SIG_BYTES];
        size_t siglen = 0;
        if (crypto_sign_signature(sig, &siglen, msg, mlen, NULL, 0, sk) != 0) {
            fprintf(stderr, "sign failed\n");
            return 1;
        }
        char *sig_hex = (char*)malloc(siglen * 2 + 1);
        bytes2hex(sig, siglen, sig_hex);
        printf("%s\n", sig_hex);
        free(sig_hex);
        return 0;
    }

    if (strcmp(argv[1], "verify") == 0 && argc >= 5) {
        uint8_t pk[PK_BYTES];
        hex2bytes(argv[2], pk, PK_BYTES);

        uint8_t sig[SIG_BYTES];
        hex2bytes(argv[3], sig, SIG_BYTES);

        uint8_t msg[4096];
        size_t mlen = hex2bytes(argv[4], msg, sizeof(msg));

        int ok = crypto_sign_verify(sig, SIG_BYTES, msg, mlen, NULL, 0, pk);
        printf("%s\n", ok == 0 ? "OK" : "FAIL");
        return ok == 0 ? 0 : 1;
    }

    fprintf(stderr, "Unknown command: %s\n", argv[1]);
    return 1;
}
