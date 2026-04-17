#ifndef BITCOIN_CRYPTO_PQC_FALCON_H
#define BITCOIN_CRYPTO_PQC_FALCON_H

#include <stdint.h>
#include <cstddef>
#include <vector>

namespace pqc {

/**
 * Falcon-padded-512 / FN-DSA digital signature scheme.
 *
 * Wraps the vendored PQClean Falcon-padded-512 reference implementation.
 * Source: https://github.com/PQClean/PQClean (FALCONPADDED512_CLEAN)
 * The padded variant produces fixed-size 666-byte signatures, which is
 * essential for deterministic witness size validation on-chain.
 *
 * Security level: NIST Level 1 (128-bit post-quantum security).
 * Standard: FIPS 206 (FN-DSA), finalized August 2024.
 *
 * Key advantage over Dilithium (ML-DSA-44):
 *   Signature: 666 bytes vs 2420 bytes (3.6× smaller)
 *   Public key: 897 bytes vs 1312 bytes (1.5× smaller)
 *
 * ─── Constant-Time Security Properties ──────────────────────────────────────
 *
 * PQClean mandates that all submitted implementations satisfy constant-time
 * requirements: no data-dependent branches or memory access patterns on
 * secret data.  The CLEAN (portable C) variant used here is reviewed and
 * accepted by the PQClean maintainers against that requirement.
 *
 * Both sign and verify paths call `hash_to_point_ct()` exclusively — the
 * constant-time variant of the message hashing step.  The vartime counterpart
 * (`hash_to_point_vartime`) exists in common.c but is not reachable from any
 * public API path (crypto_sign_signature / crypto_sign_verify in pqclean.c).
 *
 * ─── Side-Channel Scope ──────────────────────────────────────────────────────
 *
 * The CT guarantee covers software timing channels on conventional CPUs.
 * Power-analysis and electromagnetic side-channel attacks (relevant for
 * hardware security modules) are outside scope for a software full node.
 * Users deploying signing in hardware (HSM, smartcard) must evaluate
 * hardware-layer countermeasures independently.
 *
 * ─── Upgrade Path (Falcon-1024) ──────────────────────────────────────────────
 *
 * This implementation vendors both Falcon-512 (128-bit PQ, NIST Level 1)
 * and Falcon-1024 (256-bit PQ, NIST Level 5).  Use `-pqcsig=falcon1024`
 * to activate the higher-security scheme for vault outputs.
 * Falcon-1024: pk=1793 B, sig=1280 B, sk=2305 B.
 */
class Falcon {
public:
    static constexpr size_t PUBLIC_KEY_SIZE  = 897;   // FN-DSA-padded-512 public key
    static constexpr size_t PRIVATE_KEY_SIZE = 1281;  // FN-DSA-padded-512 secret key
    static constexpr size_t SIGNATURE_SIZE   = 666;   // FN-DSA-padded-512 signature (fixed)
    static constexpr size_t SEED_SIZE        = 48;    // seed for deterministic keygen

    Falcon();
    ~Falcon();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool DeriveKeyPair(const std::vector<uint8_t>& seed, std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

/**
 * Falcon-padded-1024 / FN-DSA-1024 — NIST Level 5 (256-bit post-quantum).
 *
 * Source: PQClean FALCONPADDED1024_CLEAN (src/crypto/pqc/falcon-padded-1024/).
 * Sizes: pk=1793 B, sig=1280 B (fixed/padded), sk=2305 B.
 * Use via -pqcsig=falcon1024 for high-value / vault outputs.
 *
 * Same constant-time and side-channel properties as Falcon-512 — see the
 * security notes above.  Both sign and verify use hash_to_point_ct().
 */
class Falcon1024 {
public:
    static constexpr size_t PUBLIC_KEY_SIZE  = 1793;  // FN-DSA-padded-1024 public key
    static constexpr size_t PRIVATE_KEY_SIZE = 2305;  // FN-DSA-padded-1024 secret key
    static constexpr size_t SIGNATURE_SIZE   = 1280;  // FN-DSA-padded-1024 signature (fixed)
    static constexpr size_t SEED_SIZE        = 48;    // seed for deterministic keygen

    Falcon1024();
    ~Falcon1024();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool DeriveKeyPair(const std::vector<uint8_t>& seed, std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_FALCON_H
