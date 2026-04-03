// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/pqc/ntru.h>
#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

#include <cstring>

BOOST_FIXTURE_TEST_SUITE(pqc_ntru_fo_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(ntru_size_constants)
{
    // Verify size constants are self-consistent with the FO secret key layout
    BOOST_CHECK_EQUAL(NTRU_PUBLIC_KEY_BYTES,  static_cast<int>(NTRU_N * 2));
    BOOST_CHECK_EQUAL(NTRU_CIPHERTEXT_BYTES,  static_cast<int>(NTRU_N * 2));
    BOOST_CHECK_EQUAL(NTRU_SECRET_KEY_BYTES,  static_cast<int>(NTRU_N * 2 + NTRU_PUBLIC_KEY_BYTES + 32));
    BOOST_CHECK_EQUAL(NTRU_SHARED_SECRET_BYTES, static_cast<int>(32));
}

BOOST_AUTO_TEST_CASE(ntru_roundtrip)
{
    // NOTE: The underlying NTRU IND-CPA core has a known broken poly_invert
    // (separate TODO item). This test exercises the FO transform plumbing and
    // verifies the functions run without crashing.  The shared-secret equality
    // check is a soft BOOST_CHECK so the suite continues if IND-CPA is broken.
    unsigned char pk[NTRU_PUBLIC_KEY_BYTES];
    unsigned char sk[NTRU_SECRET_KEY_BYTES];
    unsigned char ct[NTRU_CIPHERTEXT_BYTES];
    unsigned char ss_enc[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss_dec[NTRU_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::NTRU::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::NTRU::Encaps(ct, ss_enc, pk));
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss_dec, ct, sk));

    // Soft check: shared secrets should match when IND-CPA is correct.
    // Known to fail with the current broken poly_invert (separate fix tracked).
    BOOST_CHECK_EQUAL(memcmp(ss_enc, ss_dec, NTRU_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(ntru_tampered_ciphertext)
{
    // The FO transform must produce *different* shared secrets for different
    // ciphertexts decapsulated with the same key.  This holds even when the
    // underlying IND-CPA is broken because implicit rejection is:
    //   ss = SHA256(z || ct)
    // which is distinct for distinct ct values.
    unsigned char pk[NTRU_PUBLIC_KEY_BYTES];
    unsigned char sk[NTRU_SECRET_KEY_BYTES];
    unsigned char ct[NTRU_CIPHERTEXT_BYTES];
    unsigned char ct_tampered[NTRU_CIPHERTEXT_BYTES];
    unsigned char ss_enc[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss_dec_orig[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss_dec_tampered[NTRU_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::NTRU::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::NTRU::Encaps(ct, ss_enc, pk));

    // Tamper a copy of the ciphertext
    memcpy(ct_tampered, ct, NTRU_CIPHERTEXT_BYTES);
    ct_tampered[0] ^= 0xff;

    // Decapsulate both the original and tampered ciphertexts
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss_dec_orig,    ct,         sk));
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss_dec_tampered, ct_tampered, sk));

    // Different ciphertexts must yield different shared secrets (FO property)
    BOOST_CHECK_NE(memcmp(ss_dec_orig, ss_dec_tampered, NTRU_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(ntru_cross_key_mismatch)
{
    // Decapsulating ct (generated for sk1's pk) with sk2 must produce a
    // different shared secret than decapsulating with sk1.
    unsigned char pk1[NTRU_PUBLIC_KEY_BYTES];
    unsigned char sk1[NTRU_SECRET_KEY_BYTES];
    unsigned char pk2[NTRU_PUBLIC_KEY_BYTES];
    unsigned char sk2[NTRU_SECRET_KEY_BYTES];
    unsigned char ct[NTRU_CIPHERTEXT_BYTES];
    unsigned char ss_enc[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss_dec1[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss_dec2[NTRU_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::NTRU::KeyGen(pk1, sk1));
    BOOST_REQUIRE(pqc::NTRU::KeyGen(pk2, sk2));
    BOOST_REQUIRE(pqc::NTRU::Encaps(ct, ss_enc, pk1));

    BOOST_REQUIRE(pqc::NTRU::Decaps(ss_dec1, ct, sk1));
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss_dec2, ct, sk2));

    // sk1 and sk2 have independent z seeds, so rejection secrets differ
    BOOST_CHECK_NE(memcmp(ss_dec1, ss_dec2, NTRU_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(ntru_implicit_rejection_determinism)
{
    // Same (sk, ct) pair must always produce the same shared secret.
    // This validates that the implicit rejection path SHA256(z||ct) is
    // deterministic, which is required for IND-CCA2.
    unsigned char pk[NTRU_PUBLIC_KEY_BYTES];
    unsigned char sk[NTRU_SECRET_KEY_BYTES];
    unsigned char ct[NTRU_CIPHERTEXT_BYTES];
    unsigned char ss_enc[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss1[NTRU_SHARED_SECRET_BYTES];
    unsigned char ss2[NTRU_SHARED_SECRET_BYTES];

    BOOST_REQUIRE(pqc::NTRU::KeyGen(pk, sk));
    BOOST_REQUIRE(pqc::NTRU::Encaps(ct, ss_enc, pk));

    // Tamper the ciphertext to force implicit rejection
    ct[0] ^= 0xab;

    // Two calls to Decaps with identical (sk, ct) must produce the same output
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss1, ct, sk));
    BOOST_REQUIRE(pqc::NTRU::Decaps(ss2, ct, sk));

    BOOST_CHECK_EQUAL(memcmp(ss1, ss2, NTRU_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_SUITE_END()
