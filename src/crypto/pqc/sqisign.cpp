// NOT PRODUCTION — STUB ONLY: SQIsign is not implemented; all methods return false.
#include "sqisign.h"
#include <logging.h>

namespace pqc {

// SQIsign is NOT a NIST-standardized algorithm. All operations are disabled.

SQIsign::SQIsign() {}
SQIsign::~SQIsign() {}

bool SQIsign::GenerateKeyPair(std::vector<uint8_t>& /*public_key*/, std::vector<uint8_t>& /*private_key*/) {
    LogPrintf("SQIsign: algorithm not supported — not NIST standardized\n");
    return false;
}

bool SQIsign::Sign(const std::vector<uint8_t>& /*message*/, const std::vector<uint8_t>& /*private_key*/, std::vector<uint8_t>& /*signature*/) {
    LogPrintf("SQIsign: algorithm not supported — not NIST standardized\n");
    return false;
}

bool SQIsign::Verify(const std::vector<uint8_t>& /*message*/, const std::vector<uint8_t>& /*signature*/, const std::vector<uint8_t>& /*public_key*/) {
    LogPrintf("SQIsign: algorithm not supported — not NIST standardized\n");
    return false;
}

} // namespace pqc
