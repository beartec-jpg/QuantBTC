#ifndef BITCOIN_CRYPTO_PQC_ML_DSA_NTT_H
#define BITCOIN_CRYPTO_PQC_ML_DSA_NTT_H

#include <stdint.h>
#include "params.h"

#define ntt DILITHIUM_NAMESPACE(ntt)
void ntt(int32_t a[N]);

#define invntt_tomont DILITHIUM_NAMESPACE(invntt_tomont)
void invntt_tomont(int32_t a[N]);

#endif
