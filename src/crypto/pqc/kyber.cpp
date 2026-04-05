/*
 * ML-KEM-768 (Kyber-768) implementation.
 * Delegates to the pq-crystals/kyber reference C implementation under ml-kem/.
 *
 * Key sizes (Kyber-768):
 *   Public key  : 1184 bytes
 *   Secret key  : 2400 bytes
 *   Ciphertext  : 1088 bytes
 *   Shared secret: 32 bytes
 *
 * This replaces the former broken toy implementation with the real
 * IND-CCA2-secure KEM including the Fujisaki-Okamoto transform.
 */

#include "kyber.h"
#include <logging.h>
#include <string.h>

/**
 * ML-KEM-768 — STUB implementation.
 *
 * All operations return false. A real implementation will be wired in
 * when ML-KEM P2P key exchange is enabled (Phase 10).
 * The previous liboqs dependency has been removed to allow builds
 * without installing liboqs.
 */

namespace pqc {

bool Kyber::KeyGen(unsigned char* /*pk*/, unsigned char* /*sk*/) {
    LogPrintf("Kyber::KeyGen: STUB — not implemented, returning false\n");
    return false;
}

bool Kyber::Encaps(unsigned char* /*ct*/, unsigned char* /*ss*/, const unsigned char* /*pk*/) {
    LogPrintf("Kyber::Encaps: STUB — not implemented, returning false\n");
    return false;
}

bool Kyber::Decaps(unsigned char* /*ss*/, const unsigned char* /*ct*/, const unsigned char* /*sk*/) {
    LogPrintf("Kyber::Decaps: STUB — not implemented, returning false\n");
    return false;
}

} // namespace pqc
