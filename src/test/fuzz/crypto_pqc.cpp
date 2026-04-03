// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>
#include <crypto/pqc/kyber.h>
#include <crypto/pqc/ntru.h>
#include <crypto/pqc/frodokem.h>
#include <test/fuzz/FuzzedDataProvider.h>
#include <test/fuzz/fuzz.h>
#include <test/fuzz/util.h>

#include <cstdint>
#include <vector>

//! Fuzz target for ML-DSA (Dilithium) signature operations.
//! Exercises key generation, signing, and verification with
//! fuzz-supplied messages, keys, and signatures.
FUZZ_TARGET(crypto_pqc_dilithium)
{
    FuzzedDataProvider fuzzed_data_provider{buffer.data(), buffer.size()};

    // Generate a valid key pair first so we can exercise Sign/Verify.
    pqc::Dilithium dilithium;
    std::vector<uint8_t> pk, sk;

    if (fuzzed_data_provider.ConsumeBool()) {
        // Use genuinely generated keys.
        (void)dilithium.GenerateKeyPair(pk, sk);

        // Fuzz-supplied message.
        std::vector<uint8_t> message = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        if (message.empty()) {
            message.push_back(fuzzed_data_provider.ConsumeIntegral<uint8_t>());
        }

        std::vector<uint8_t> sig;
        if (dilithium.Sign(message, sk, sig)) {
            // Valid signature must verify.
            (void)dilithium.Verify(message, sig, pk);

            // Fuzz-corrupted signature must not crash.
            if (!sig.empty()) {
                sig[fuzzed_data_provider.ConsumeIntegralInRange<size_t>(0, sig.size() - 1)] ^=
                    fuzzed_data_provider.ConsumeIntegralInRange<uint8_t>(1, 255);
                (void)dilithium.Verify(message, sig, pk);
            }
        }
    } else {
        // Exercise Verify with completely fuzz-supplied inputs.
        std::vector<uint8_t> message = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> sig = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> pubkey = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        (void)dilithium.Verify(message, sig, pubkey);
    }
}

//! Fuzz target for SLH-DSA (SPHINCS+) signature operations.
FUZZ_TARGET(crypto_pqc_sphincs)
{
    FuzzedDataProvider fuzzed_data_provider{buffer.data(), buffer.size()};

    pqc::SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;

    if (fuzzed_data_provider.ConsumeBool()) {
        // Use genuinely generated keys.
        (void)sphincs.GenerateKeyPair(pk, sk);

        std::vector<uint8_t> message = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        if (message.empty()) {
            message.push_back(fuzzed_data_provider.ConsumeIntegral<uint8_t>());
        }

        std::vector<uint8_t> sig;
        if (sphincs.Sign(message, sk, sig)) {
            (void)sphincs.Verify(message, sig, pk);

            // Fuzz-corrupted signature must not crash.
            if (!sig.empty()) {
                sig[fuzzed_data_provider.ConsumeIntegralInRange<size_t>(0, sig.size() - 1)] ^=
                    fuzzed_data_provider.ConsumeIntegralInRange<uint8_t>(1, 255);
                (void)sphincs.Verify(message, sig, pk);
            }
        }
    } else {
        // Exercise Verify with completely fuzz-supplied inputs.
        std::vector<uint8_t> message = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> sig = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> pubkey = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        (void)sphincs.Verify(message, sig, pubkey);
    }
}

//! Fuzz target for ML-KEM (Kyber) key encapsulation operations.
FUZZ_TARGET(crypto_pqc_kyber)
{
    FuzzedDataProvider fuzzed_data_provider{buffer.data(), buffer.size()};

    if (fuzzed_data_provider.ConsumeBool()) {
        // Use genuinely generated keys.
        unsigned char pk[KYBER_PUBLIC_KEY_BYTES];
        unsigned char sk[KYBER_SECRET_KEY_BYTES];
        if (pqc::Kyber::KeyGen(pk, sk)) {
            unsigned char ct[KYBER_CIPHERTEXT_BYTES];
            unsigned char ss_enc[KYBER_SHARED_SECRET_BYTES];
            if (pqc::Kyber::Encaps(ct, ss_enc, pk)) {
                // Valid ciphertext must decapsulate without crashing.
                unsigned char ss_dec[KYBER_SHARED_SECRET_BYTES];
                (void)pqc::Kyber::Decaps(ss_dec, ct, sk);

                // Fuzz-corrupted ciphertext must not crash.
                ct[fuzzed_data_provider.ConsumeIntegralInRange<size_t>(0, KYBER_CIPHERTEXT_BYTES - 1)] ^=
                    fuzzed_data_provider.ConsumeIntegralInRange<uint8_t>(1, 255);
                (void)pqc::Kyber::Decaps(ss_dec, ct, sk);
            }
        }
    } else {
        // Exercise with fuzz-supplied buffers — must not crash.
        std::vector<uint8_t> pk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> sk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> ct_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);

        // Pad to expected sizes to exercise the underlying implementation.
        pk_fuzz.resize(KYBER_PUBLIC_KEY_BYTES);
        sk_fuzz.resize(KYBER_SECRET_KEY_BYTES);
        ct_fuzz.resize(KYBER_CIPHERTEXT_BYTES);

        unsigned char ct[KYBER_CIPHERTEXT_BYTES];
        unsigned char ss[KYBER_SHARED_SECRET_BYTES];
        (void)pqc::Kyber::Encaps(ct, ss, pk_fuzz.data());
        (void)pqc::Kyber::Decaps(ss, ct_fuzz.data(), sk_fuzz.data());
    }
}

//! Fuzz target for NTRU key encapsulation operations.
//! Exercises KeyGen, Encaps, and Decaps with adversarial inputs.
FUZZ_TARGET(crypto_pqc_ntru)
{
    FuzzedDataProvider fuzzed_data_provider{buffer.data(), buffer.size()};

    if (fuzzed_data_provider.ConsumeBool()) {
        // Use genuinely generated keys.
        unsigned char pk[NTRU_PUBLIC_KEY_BYTES];
        unsigned char sk[NTRU_SECRET_KEY_BYTES];
        if (pqc::NTRU::KeyGen(pk, sk)) {
            unsigned char ct[NTRU_CIPHERTEXT_BYTES];
            unsigned char ss_enc[NTRU_SHARED_SECRET_BYTES];
            if (pqc::NTRU::Encaps(ct, ss_enc, pk)) {
                // Valid ciphertext must decapsulate without crashing.
                unsigned char ss_dec[NTRU_SHARED_SECRET_BYTES];
                (void)pqc::NTRU::Decaps(ss_dec, ct, sk);

                // Fuzz-corrupted ciphertext must not crash.
                ct[fuzzed_data_provider.ConsumeIntegralInRange<size_t>(0, NTRU_CIPHERTEXT_BYTES - 1)] ^=
                    fuzzed_data_provider.ConsumeIntegralInRange<uint8_t>(1, 255);
                (void)pqc::NTRU::Decaps(ss_dec, ct, sk);
            }
        }
    } else {
        // Exercise with fuzz-supplied buffers — must not crash.
        std::vector<uint8_t> pk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> sk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> ct_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);

        // Pad to expected sizes to exercise the underlying implementation.
        pk_fuzz.resize(NTRU_PUBLIC_KEY_BYTES);
        sk_fuzz.resize(NTRU_SECRET_KEY_BYTES);
        ct_fuzz.resize(NTRU_CIPHERTEXT_BYTES);

        unsigned char ct[NTRU_CIPHERTEXT_BYTES];
        unsigned char ss[NTRU_SHARED_SECRET_BYTES];
        (void)pqc::NTRU::Encaps(ct, ss, pk_fuzz.data());
        (void)pqc::NTRU::Decaps(ss, ct_fuzz.data(), sk_fuzz.data());
    }
}

//! Fuzz target for FrodoKEM key encapsulation operations.
//! Exercises KeyGen, Encaps, and Decaps with adversarial inputs.
FUZZ_TARGET(crypto_pqc_frodokem)
{
    FuzzedDataProvider fuzzed_data_provider{buffer.data(), buffer.size()};

    if (fuzzed_data_provider.ConsumeBool()) {
        // Use genuinely generated keys.
        unsigned char pk[FRODO_PUBLIC_KEY_BYTES];
        unsigned char sk[FRODO_SECRET_KEY_BYTES];
        if (pqc::FrodoKEM::KeyGen(pk, sk)) {
            unsigned char ct[FRODO_CIPHERTEXT_BYTES];
            unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
            if (pqc::FrodoKEM::Encaps(ct, ss_enc, pk)) {
                // Valid ciphertext must decapsulate without crashing.
                unsigned char ss_dec[FRODO_SHARED_SECRET_BYTES];
                (void)pqc::FrodoKEM::Decaps(ss_dec, ct, sk);

                // Fuzz-corrupted ciphertext must not crash.
                ct[fuzzed_data_provider.ConsumeIntegralInRange<size_t>(0, FRODO_CIPHERTEXT_BYTES - 1)] ^=
                    fuzzed_data_provider.ConsumeIntegralInRange<uint8_t>(1, 255);
                (void)pqc::FrodoKEM::Decaps(ss_dec, ct, sk);
            }
        }
    } else {
        // Exercise with fuzz-supplied buffers — must not crash.
        std::vector<uint8_t> pk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> sk_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);
        std::vector<uint8_t> ct_fuzz = ConsumeRandomLengthByteVector(fuzzed_data_provider);

        // Pad to expected sizes to exercise the underlying implementation.
        pk_fuzz.resize(FRODO_PUBLIC_KEY_BYTES);
        sk_fuzz.resize(FRODO_SECRET_KEY_BYTES);
        ct_fuzz.resize(FRODO_CIPHERTEXT_BYTES);

        unsigned char ct[FRODO_CIPHERTEXT_BYTES];
        unsigned char ss[FRODO_SHARED_SECRET_BYTES];
        (void)pqc::FrodoKEM::Encaps(ct, ss, pk_fuzz.data());
        (void)pqc::FrodoKEM::Decaps(ss, ct_fuzz.data(), sk_fuzz.data());
    }
}
