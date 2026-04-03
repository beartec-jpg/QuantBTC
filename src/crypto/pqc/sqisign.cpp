#include "sqisign.h"
#include <logging.h>

namespace pqc {

SQIsign::SQIsign() {}
SQIsign::~SQIsign() {}

bool SQIsign::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    LogPrintf("SQIsign::GenerateKeyPair: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

bool SQIsign::Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature) {
    LogPrintf("SQIsign::Sign: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

bool SQIsign::Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key) {
    LogPrintf("SQIsign::Verify: NOT IMPLEMENTED — algorithm disabled\n");
    return false;
}

} // namespace pqc
