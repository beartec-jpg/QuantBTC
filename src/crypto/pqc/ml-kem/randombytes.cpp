/* Bitcoin Core random bytes provider for ML-KEM-768 (Kyber-768) reference implementation.
 * Bridges the C randombytes() API to Bitcoin Core's GetStrongRandBytes().
 */
#include "randombytes.h"
#include <random.h>
#include <span.h>

void randombytes(uint8_t *out, size_t outlen)
{
    GetStrongRandBytes(Span<unsigned char>(out, outlen));
}
