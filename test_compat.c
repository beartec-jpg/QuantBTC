/* Cross-compatibility test: QBTC node ML-DSA-44 vs noble/post-quantum.
 * Given a hex seed on argv[1] and hex message on argv[2]:
 *   - derive keypair from seed
 *   - sign message
 *   - verify signature
 *   - print pk_hex, sig_hex for comparison with noble output
 * If argv[3] is provided (hex signature from noble) and argv[4] (hex pubkey from noble):
 *   - verify noble's signature against the provided pubkey
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "src/crypto/pqc/ml-dsa/sign.h"
#include "src/crypto/pqc/ml-dsa/params.h"

/* Stub: we only use seed_keypair (deterministic), not random keypair */
void randombytes(uint8_t *out, size_t outlen) {
    memset(out, 0, outlen);
}

static int hex2bin(const char *hex, uint8_t *out, size_t outlen) {
    size_t hexlen = strlen(hex);
    if (hexlen != outlen * 2) return -1;
    for (size_t i = 0; i < outlen; i++) {
        unsigned int val;
        if (sscanf(hex + 2*i, "%02x", &val) != 1) return -1;
        out[i] = (uint8_t)val;
    }
    return 0;
}

static void bin2hex(const uint8_t *in, size_t len, char *out) {
    for (size_t i = 0; i < len; i++)
        sprintf(out + 2*i, "%02x", in[i]);
    out[len*2] = '\0';
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <seed_hex_32B> <msg_hex> [noble_sig_hex] [noble_pk_hex]\n", argv[0]);
        return 1;
    }

    /* Parse seed */
    uint8_t seed[32];
    if (hex2bin(argv[1], seed, 32) != 0) {
        fprintf(stderr, "Invalid seed hex (need 64 hex chars)\n");
        return 1;
    }

    /* Parse message */
    size_t msg_hex_len = strlen(argv[2]);
    size_t msg_len = msg_hex_len / 2;
    uint8_t *msg = malloc(msg_len);
    if (hex2bin(argv[2], msg, msg_len) != 0) {
        fprintf(stderr, "Invalid message hex\n");
        return 1;
    }

    /* Derive keypair from seed */
    uint8_t pk[CRYPTO_PUBLICKEYBYTES];
    uint8_t sk[CRYPTO_SECRETKEYBYTES];
    if (crypto_sign_seed_keypair(pk, sk, seed) != 0) {
        fprintf(stderr, "crypto_sign_seed_keypair failed\n");
        return 1;
    }

    /* Print public key (first 64 bytes for comparison) */
    char *pk_hex = malloc(CRYPTO_PUBLICKEYBYTES * 2 + 1);
    bin2hex(pk, CRYPTO_PUBLICKEYBYTES, pk_hex);
    printf("NODE_PK=%s\n", pk_hex);
    printf("NODE_PK_SIZE=%d\n", CRYPTO_PUBLICKEYBYTES);

    /* Sign message */
    uint8_t sig[CRYPTO_BYTES];
    size_t siglen = 0;
    if (crypto_sign_signature(sig, &siglen, msg, msg_len, NULL, 0, sk) != 0) {
        fprintf(stderr, "crypto_sign_signature failed\n");
        return 1;
    }
    printf("NODE_SIG_SIZE=%zu\n", siglen);

    char *sig_hex = malloc(siglen * 2 + 1);
    bin2hex(sig, siglen, sig_hex);
    printf("NODE_SIG=%s\n", sig_hex);

    /* Self-verify */
    int rv = crypto_sign_verify(sig, siglen, msg, msg_len, NULL, 0, pk);
    printf("NODE_SELF_VERIFY=%s\n", rv == 0 ? "OK" : "FAIL");

    /* If noble sig/pk provided, cross-verify */
    if (argc >= 5) {
        size_t noble_sig_hex_len = strlen(argv[3]);
        size_t noble_sig_len = noble_sig_hex_len / 2;
        uint8_t *noble_sig = malloc(noble_sig_len);
        if (hex2bin(argv[3], noble_sig, noble_sig_len) != 0) {
            fprintf(stderr, "Invalid noble sig hex\n");
            return 1;
        }

        size_t noble_pk_hex_len = strlen(argv[4]);
        size_t noble_pk_len = noble_pk_hex_len / 2;
        uint8_t *noble_pk = malloc(noble_pk_len);
        if (hex2bin(argv[4], noble_pk, noble_pk_len) != 0) {
            fprintf(stderr, "Invalid noble pk hex\n");
            return 1;
        }

        printf("NOBLE_SIG_SIZE=%zu\n", noble_sig_len);
        printf("NOBLE_PK_SIZE=%zu\n", noble_pk_len);

        /* Check if public keys match */
        if (noble_pk_len == CRYPTO_PUBLICKEYBYTES && memcmp(pk, noble_pk, CRYPTO_PUBLICKEYBYTES) == 0) {
            printf("PK_MATCH=YES\n");
        } else {
            printf("PK_MATCH=NO\n");
            /* Print first 32 bytes of each for comparison */
            char buf[65];
            bin2hex(pk, 32, buf);
            printf("NODE_PK_FIRST32=%s\n", buf);
            bin2hex(noble_pk, 32 < noble_pk_len ? 32 : noble_pk_len, buf);
            printf("NOBLE_PK_FIRST32=%s\n", buf);
        }

        /* Verify noble's signature with noble's public key */
        rv = crypto_sign_verify(noble_sig, noble_sig_len, msg, msg_len, NULL, 0, noble_pk);
        printf("NODE_VERIFY_NOBLE_SIG_WITH_NOBLE_PK=%s\n", rv == 0 ? "OK" : "FAIL");

        /* Verify noble's signature with node's public key (if they differ) */
        if (noble_pk_len == CRYPTO_PUBLICKEYBYTES && memcmp(pk, noble_pk, CRYPTO_PUBLICKEYBYTES) != 0) {
            rv = crypto_sign_verify(noble_sig, noble_sig_len, msg, msg_len, NULL, 0, pk);
            printf("NODE_VERIFY_NOBLE_SIG_WITH_NODE_PK=%s\n", rv == 0 ? "OK" : "FAIL");
        }

        free(noble_sig);
        free(noble_pk);
    }

    free(msg);
    free(pk_hex);
    free(sig_hex);
    return 0;
}
