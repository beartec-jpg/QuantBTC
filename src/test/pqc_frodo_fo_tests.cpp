// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/pqc/frodokem.h>
#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

#include <cstring>

BOOST_FIXTURE_TEST_SUITE(pqc_frodo_fo_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(frodo_size_constants)
{
    // Verify size constants are self-consistent with the FO secret key layout
    BOOST_CHECK_EQUAL(FRODO_PUBLIC_KEY_BYTES,      static_cast<int>(32 + 2 * FRODO_N * FRODO_NBAR));
    BOOST_CHECK_EQUAL(FRODO_SECRET_KEY_BYTES,
                      static_cast<int>(2 * FRODO_N * FRODO_NBAR + FRODO_PUBLIC_KEY_BYTES + 32 + 32));
    BOOST_CHECK_EQUAL(FRODO_CIPHERTEXT_BYTES,
                      static_cast<int>(2 * FRODO_MBAR * FRODO_N + 2 * FRODO_MBAR * FRODO_NBAR));
    BOOST_CHECK_EQUAL(FRODO_SHARED_SECRET_BYTES, static_cast<int>(32));
}

BOOST_AUTO_TEST_CASE(frodo_roundtrip)
{
    // Also verifies no stack overflow: KeyGen and Encaps previously allocated
    // ~1.86 MB (uint16_t A[976*976]) on the stack, which would segfault.
    unsigned char pk[FRODO_PUBLIC_KEY_BYTES];
    unsigned char sk[FRODO_SECRET_KEY_BYTES];
    unsigned char ct[FRODO_CIPHERTEXT_BYTES];
    unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_dec[FRODO_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::FrodoKEM::Encaps(ct, ss_enc, pk));
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_dec, ct, sk));

    // Shared secrets produced by Encaps and Decaps must match
    BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec, FRODO_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(frodo_multiple_roundtrips)
{
    for (int i = 0; i < 2; ++i) {
        unsigned char pk[FRODO_PUBLIC_KEY_BYTES];
        unsigned char sk[FRODO_SECRET_KEY_BYTES];
        unsigned char ct[FRODO_CIPHERTEXT_BYTES];
        unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
        unsigned char ss_dec[FRODO_SHARED_SECRET_BYTES];

        BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk, sk));
        BOOST_REQUIRE(pqc::FrodoKEM::Encaps(ct, ss_enc, pk));
        BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_dec, ct, sk));

        BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec, FRODO_SHARED_SECRET_BYTES), 0);
    }
}

BOOST_AUTO_TEST_CASE(frodo_tampered_ciphertext)
{
    // FO transform: tampered ciphertext must produce a *different* shared
    // secret (implicit rejection), not a decapsulation failure.
    unsigned char pk[FRODO_PUBLIC_KEY_BYTES];
    unsigned char sk[FRODO_SECRET_KEY_BYTES];
    unsigned char ct[FRODO_CIPHERTEXT_BYTES];
    unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_dec_good[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_dec_bad[FRODO_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::FrodoKEM::Encaps(ct, ss_enc, pk));

    // Decapsulate the untampered ciphertext — must match ss_enc
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_dec_good, ct, sk));
    BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec_good, FRODO_SHARED_SECRET_BYTES), 0);

    // Flip a byte in the ciphertext
    ct[0] ^= 0xff;

    // Decapsulate the tampered ciphertext — must still return true (implicit
    // rejection) but produce a different shared secret.
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_dec_bad, ct, sk));
    BOOST_CHECK_NE(memcmp(ss_enc, ss_dec_bad, FRODO_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(frodo_cross_key_mismatch)
{
    // Encapsulating to pk1 and decapsulating with sk2 must produce a
    // different shared secret.
    unsigned char pk1[FRODO_PUBLIC_KEY_BYTES];
    unsigned char sk1[FRODO_SECRET_KEY_BYTES];
    unsigned char pk2[FRODO_PUBLIC_KEY_BYTES];
    unsigned char sk2[FRODO_SECRET_KEY_BYTES];
    unsigned char ct[FRODO_CIPHERTEXT_BYTES];
    unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_dec_wrong[FRODO_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk1, sk1));
    BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk2, sk2));
    BOOST_REQUIRE(pqc::FrodoKEM::Encaps(ct, ss_enc, pk1));
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_dec_wrong, ct, sk2));

    BOOST_CHECK_NE(memcmp(ss_enc, ss_dec_wrong, FRODO_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(frodo_implicit_rejection_determinism)
{
    // Same (sk, tampered_ct) must always produce the same rejection shared secret.
    unsigned char pk[FRODO_PUBLIC_KEY_BYTES];
    unsigned char sk[FRODO_SECRET_KEY_BYTES];
    unsigned char ct[FRODO_CIPHERTEXT_BYTES];
    unsigned char ss_enc[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_bad1[FRODO_SHARED_SECRET_BYTES];
    unsigned char ss_bad2[FRODO_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::FrodoKEM::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::FrodoKEM::Encaps(ct, ss_enc, pk));

    // Tamper ciphertext
    ct[0] ^= 0xab;

    // Two decapsulations of the same tampered ct with the same sk
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_bad1, ct, sk));
    BOOST_REQUIRE(pqc::FrodoKEM::Decaps(ss_bad2, ct, sk));

    // Rejection output must be deterministic
    BOOST_CHECK_EQUAL(memcmp(ss_bad1, ss_bad2, FRODO_SHARED_SECRET_BYTES), 0);
    // And must differ from the real shared secret
    BOOST_CHECK_NE(memcmp(ss_enc, ss_bad1, FRODO_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_SUITE_END()
