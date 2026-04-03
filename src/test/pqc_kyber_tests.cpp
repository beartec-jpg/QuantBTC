// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/pqc/kyber.h>
#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

#include <cstring>

BOOST_FIXTURE_TEST_SUITE(pqc_kyber_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(kyber_size_constants)
{
    // Verify size constants match ML-KEM-768 (Kyber-768) specification
    BOOST_CHECK_EQUAL(KYBER_PUBLIC_KEY_BYTES,   static_cast<int>(1184));
    BOOST_CHECK_EQUAL(KYBER_SECRET_KEY_BYTES,   static_cast<int>(2400));
    BOOST_CHECK_EQUAL(KYBER_CIPHERTEXT_BYTES,   static_cast<int>(1088));
    BOOST_CHECK_EQUAL(KYBER_SHARED_SECRET_BYTES, static_cast<int>(32));
}

BOOST_AUTO_TEST_CASE(kyber_roundtrip)
{
    unsigned char pk[KYBER_PUBLIC_KEY_BYTES];
    unsigned char sk[KYBER_SECRET_KEY_BYTES];
    unsigned char ct[KYBER_CIPHERTEXT_BYTES];
    unsigned char ss_enc[KYBER_SHARED_SECRET_BYTES];
    unsigned char ss_dec[KYBER_SHARED_SECRET_BYTES];

    // Key generation must succeed
    BOOST_REQUIRE(pqc::Kyber::KeyGen(pk, sk));

    // Encapsulation must succeed
    BOOST_REQUIRE(pqc::Kyber::Encaps(ct, ss_enc, pk));

    // Decapsulation must succeed
    BOOST_REQUIRE(pqc::Kyber::Decaps(ss_dec, ct, sk));

    // Shared secrets produced by Encaps and Decaps must match
    BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec, KYBER_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(kyber_multiple_roundtrips)
{
    // Run several independent round-trips to verify consistency
    for (int i = 0; i < 3; ++i) {
        unsigned char pk[KYBER_PUBLIC_KEY_BYTES];
        unsigned char sk[KYBER_SECRET_KEY_BYTES];
        unsigned char ct[KYBER_CIPHERTEXT_BYTES];
        unsigned char ss_enc[KYBER_SHARED_SECRET_BYTES];
        unsigned char ss_dec[KYBER_SHARED_SECRET_BYTES];

        BOOST_REQUIRE(pqc::Kyber::KeyGen(pk, sk));
        BOOST_REQUIRE(pqc::Kyber::Encaps(ct, ss_enc, pk));
        BOOST_REQUIRE(pqc::Kyber::Decaps(ss_dec, ct, sk));

        BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec, KYBER_SHARED_SECRET_BYTES), 0);
    }
}

BOOST_AUTO_TEST_CASE(kyber_tampered_ciphertext)
{
    // The FO transform must produce a different (pseudo-random) shared secret
    // when the ciphertext has been tampered with.
    unsigned char pk[KYBER_PUBLIC_KEY_BYTES];
    unsigned char sk[KYBER_SECRET_KEY_BYTES];
    unsigned char ct[KYBER_CIPHERTEXT_BYTES];
    unsigned char ss_enc[KYBER_SHARED_SECRET_BYTES];
    unsigned char ss_dec_good[KYBER_SHARED_SECRET_BYTES];
    unsigned char ss_dec_bad[KYBER_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::Kyber::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::Kyber::Encaps(ct, ss_enc, pk));

    // Decapsulate the untampered ciphertext — must match ss_enc
    BOOST_REQUIRE(pqc::Kyber::Decaps(ss_dec_good, ct, sk));
    BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec_good, KYBER_SHARED_SECRET_BYTES), 0);

    // Flip a byte in the ciphertext
    ct[0] ^= 0xff;

    // Decapsulate the tampered ciphertext — must still succeed (IND-CCA2
    // Fujisaki-Okamoto: return pseudorandom secret on mismatch) but produce
    // a different shared secret.
    BOOST_REQUIRE(pqc::Kyber::Decaps(ss_dec_bad, ct, sk));
    BOOST_CHECK_NE(memcmp(ss_enc, ss_dec_bad, KYBER_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(kyber_cross_key_mismatch)
{
    // Encapsulating to pk1 and decapsulating with sk2 must produce different
    // shared secrets (basic correctness / key isolation).
    unsigned char pk1[KYBER_PUBLIC_KEY_BYTES];
    unsigned char sk1[KYBER_SECRET_KEY_BYTES];
    unsigned char pk2[KYBER_PUBLIC_KEY_BYTES];
    unsigned char sk2[KYBER_SECRET_KEY_BYTES];
    unsigned char ct[KYBER_CIPHERTEXT_BYTES];
    unsigned char ss_enc[KYBER_SHARED_SECRET_BYTES];
    unsigned char ss_dec_wrong[KYBER_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::Kyber::KeyGen(pk1, sk1));
    BOOST_REQUIRE(pqc::Kyber::KeyGen(pk2, sk2));
    BOOST_REQUIRE(pqc::Kyber::Encaps(ct, ss_enc, pk1));
    BOOST_REQUIRE(pqc::Kyber::Decaps(ss_dec_wrong, ct, sk2));

    BOOST_CHECK_NE(memcmp(ss_enc, ss_dec_wrong, KYBER_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_SUITE_END()
