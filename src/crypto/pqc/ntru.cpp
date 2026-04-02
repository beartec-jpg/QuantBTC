#include "ntru.h"
#include <logging.h>

namespace pqc {

// NTRU-HPS was NOT selected by NIST for standardization.
// This algorithm is disabled. Use ML-KEM-768 (Kyber) instead.

bool NTRU::KeyGen(unsigned char* /*pk*/, unsigned char* /*sk*/) {
    LogPrintf("NTRU: algorithm not supported — use ML-KEM-768 instead\n");
    return false;
}

bool NTRU::Encaps(unsigned char* /*ct*/, unsigned char* /*ss*/, const unsigned char* /*pk*/) {
    LogPrintf("NTRU: algorithm not supported — use ML-KEM-768 instead\n");
    return false;
}

bool NTRU::Decaps(unsigned char* /*ss*/, const unsigned char* /*ct*/, const unsigned char* /*sk*/) {
    LogPrintf("NTRU: algorithm not supported — use ML-KEM-768 instead\n");
    return false;
}

} // namespace pqc
