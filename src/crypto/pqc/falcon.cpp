// STUB ONLY: Falcon/FN-DSA is not yet implemented; all methods return false.
// liboqs dependency removed — will be replaced with vendored implementation.
#include "falcon.h"
#include <logging.h>

namespace pqc {

Falcon::Falcon() {}
Falcon::~Falcon() {}

bool Falcon::GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key) {
    LogPrintf("Falcon::GenerateKeyPair: STUB — not implemented, returning false\n");
    public_key.clear();
    private_key.clear();
    return false;
}

bool Falcon::Sign(const std::vector<uint8_t>& /*message*/, const std::vector<uint8_t>& /*private_key*/, std::vector<uint8_t>& signature) {
    LogPrintf("Falcon::Sign: STUB — not implemented, returning false\n");
    signature.clear();
    return false;
}

bool Falcon::Verify(const std::vector<uint8_t>& /*message*/, const std::vector<uint8_t>& /*signature*/, const std::vector<uint8_t>& /*public_key*/) {
    LogPrintf("Falcon::Verify: STUB — not implemented, returning false\n");
    return false;
}

} // namespace pqc
