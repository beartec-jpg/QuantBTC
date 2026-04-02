// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <crypto/pqc/sphincs.h>
#include <test/util/setup_common.h>

#include <boost/test/unit_test.hpp>

#include <vector>

using namespace pqc;

BOOST_FIXTURE_TEST_SUITE(pqc_sphincs_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(sphincs_size_constants)
{
    // Verify that the size constants match the SLH-DSA-SHA2-128f parameter set
    BOOST_CHECK_EQUAL(SPHINCS::PUBLIC_KEY_SIZE, static_cast<size_t>(32));
    BOOST_CHECK_EQUAL(SPHINCS::PRIVATE_KEY_SIZE, static_cast<size_t>(64));
    BOOST_CHECK_EQUAL(SPHINCS::SIGNATURE_SIZE, static_cast<size_t>(17088));
}

BOOST_AUTO_TEST_CASE(sphincs_keygen_sizes)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;

    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk, sk));

    BOOST_CHECK_EQUAL(pk.size(), SPHINCS::PUBLIC_KEY_SIZE);
    BOOST_CHECK_EQUAL(sk.size(), SPHINCS::PRIVATE_KEY_SIZE);
}

BOOST_AUTO_TEST_CASE(sphincs_sign_verify_roundtrip)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk, sk));

    const std::vector<uint8_t> message = {0x01, 0x02, 0x03, 0x04, 0x05};
    std::vector<uint8_t> sig;

    BOOST_REQUIRE(sphincs.Sign(message, sk, sig));
    BOOST_CHECK_EQUAL(sig.size(), SPHINCS::SIGNATURE_SIZE);

    BOOST_CHECK(sphincs.Verify(message, sig, pk));
}

BOOST_AUTO_TEST_CASE(sphincs_verify_fails_tampered_message)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk, sk));

    std::vector<uint8_t> message = {0xde, 0xad, 0xbe, 0xef};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(sphincs.Sign(message, sk, sig));

    // Flip a byte in the message
    message[0] ^= 0xff;
    BOOST_CHECK(!sphincs.Verify(message, sig, pk));
}

BOOST_AUTO_TEST_CASE(sphincs_verify_fails_wrong_public_key)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk1, sk1;
    std::vector<uint8_t> pk2, sk2;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk1, sk1));
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk2, sk2));

    const std::vector<uint8_t> message = {0xca, 0xfe, 0xba, 0xbe};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(sphincs.Sign(message, sk1, sig));

    // Verify with the wrong public key must fail
    BOOST_CHECK(!sphincs.Verify(message, sig, pk2));
}

BOOST_AUTO_TEST_CASE(sphincs_verify_fails_tampered_signature)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk, sk));

    const std::vector<uint8_t> message = {0x11, 0x22, 0x33};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(sphincs.Sign(message, sk, sig));

    // Flip a byte in the signature
    sig[0] ^= 0xff;
    BOOST_CHECK(!sphincs.Verify(message, sig, pk));
}

BOOST_AUTO_TEST_CASE(sphincs_sign_rejects_wrong_key_size)
{
    SPHINCS sphincs;
    const std::vector<uint8_t> message = {0x01};
    std::vector<uint8_t> sig;

    // Too short private key must fail
    std::vector<uint8_t> bad_sk(SPHINCS::PRIVATE_KEY_SIZE - 1, 0x00);
    BOOST_CHECK(!sphincs.Sign(message, bad_sk, sig));
}

BOOST_AUTO_TEST_CASE(sphincs_verify_rejects_wrong_sizes)
{
    SPHINCS sphincs;
    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(pk, sk));

    const std::vector<uint8_t> message = {0x42};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(sphincs.Sign(message, sk, sig));

    // Wrong public key size
    std::vector<uint8_t> bad_pk(SPHINCS::PUBLIC_KEY_SIZE - 1, 0x00);
    BOOST_CHECK(!sphincs.Verify(message, sig, bad_pk));

    // Wrong signature size
    std::vector<uint8_t> bad_sig(SPHINCS::SIGNATURE_SIZE - 1, 0x00);
    BOOST_CHECK(!sphincs.Verify(message, bad_sig, pk));
}

BOOST_AUTO_TEST_SUITE_END()
