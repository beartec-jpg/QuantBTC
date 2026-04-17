/* Bitcoin Core random bytes provider for all PQC reference implementations
 * (ML-DSA, ML-KEM, SPHINCS+).  Bridges the C randombytes() API to Bitcoin
 * Core's GetStrongRandBytes().
 *
 * This is the ONLY definition of the C-linkage randombytes symbol in the
 * build.  The three vendored C libraries (ml-dsa, ml-kem, sphincsplus) all
 * resolve to this single implementation.
 */
#include "randombytes.h"
#include <random.h>
#include <span.h>

extern "C" {
void randombytes(uint8_t *out, size_t outlen)
{
    // GetStrongRandBytes supports up to 32 bytes per call. Process in chunks.
    while (outlen > 0) {
        size_t chunk = outlen < 32 ? outlen : 32;
        GetStrongRandBytes(Span<unsigned char>(out, chunk));
        out += chunk;
        outlen -= chunk;
    }
}
} // extern "C"
