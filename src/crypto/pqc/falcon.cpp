// NOT PRODUCTION — STUB ONLY: Falcon is not implemented; all methods return false.
#include "falcon.h"
#include <logging.h>

namespace pqc {

// NOT PRODUCTION: placeholder Falcon implementation.

Falcon::Falcon() {}
Falcon::~Falcon() {}

bool Falcon::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    LogPrintf("Falcon::GenerateKeyPair: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

bool Falcon::Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature) {
    LogPrintf("Falcon::Sign: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

bool Falcon::Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key) {
    LogPrintf("Falcon::Verify: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

} // namespace pqc
