#include "frodokem.h"

#include <logging.h>

namespace pqc {

// FrodoKEM was not selected by NIST for standardization.
// The previous experimental implementation in this tree was not buildable.
// Keep the API intact but disable the algorithm until a consistent
// implementation is restored.

bool FrodoKEM::KeyGen(unsigned char* /*pk*/, unsigned char* /*sk*/)
{
    LogPrintf("FrodoKEM: algorithm not supported in this build\n");
    return false;
}

bool FrodoKEM::Encaps(unsigned char* /*ct*/, unsigned char* /*ss*/, const unsigned char* /*pk*/)
{
    LogPrintf("FrodoKEM: algorithm not supported in this build\n");
    return false;
}

bool FrodoKEM::Decaps(unsigned char* /*ss*/, const unsigned char* /*ct*/, const unsigned char* /*sk*/)
{
    LogPrintf("FrodoKEM: algorithm not supported in this build\n");
    return false;
}

} // namespace pqc
