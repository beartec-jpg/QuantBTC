/* Vendored from pq-crystals/dilithium (ref/) - MIT/CC0 licensed.
 * Hardcoded for Dilithium2 (ML-DSA-44) mode only.
 * Randomized signing is disabled for deterministic Bitcoin transaction signing.
 */
#ifndef BITCOIN_CRYPTO_PQC_ML_DSA_CONFIG_H
#define BITCOIN_CRYPTO_PQC_ML_DSA_CONFIG_H

#define DILITHIUM_MODE 2
/* Deterministic (non-randomized) signing */
/* #define DILITHIUM_RANDOMIZED_SIGNING */

#if DILITHIUM_MODE == 2
#define CRYPTO_ALGNAME "Dilithium2"
#define DILITHIUM_NAMESPACETOP pqcrystals_dilithium2_ref
#define DILITHIUM_NAMESPACE(s) pqcrystals_dilithium2_ref_##s
#elif DILITHIUM_MODE == 3
#define CRYPTO_ALGNAME "Dilithium3"
#define DILITHIUM_NAMESPACETOP pqcrystals_dilithium3_ref
#define DILITHIUM_NAMESPACE(s) pqcrystals_dilithium3_ref_##s
#elif DILITHIUM_MODE == 5
#define CRYPTO_ALGNAME "Dilithium5"
#define DILITHIUM_NAMESPACETOP pqcrystals_dilithium5_ref
#define DILITHIUM_NAMESPACE(s) pqcrystals_dilithium5_ref_##s
#endif

#endif
