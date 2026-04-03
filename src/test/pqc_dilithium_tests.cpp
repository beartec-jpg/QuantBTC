#include <boost/test/unit_test.hpp>
#include <crypto/pqc/dilithium.h>
#include <vector>
#include <cstring>

BOOST_AUTO_TEST_SUITE(pqc_dilithium_tests)

// Verify the declared size constants match the real ML-DSA-44 reference sizes
BOOST_AUTO_TEST_CASE(size_constants)
{
    BOOST_CHECK_EQUAL(pqc::Dilithium::PUBLIC_KEY_SIZE,  1312U);
    BOOST_CHECK_EQUAL(pqc::Dilithium::PRIVATE_KEY_SIZE, 2560U);
    BOOST_CHECK_EQUAL(pqc::Dilithium::SIGNATURE_SIZE,   2420U);
}

// Full sign / verify round-trip with a randomly generated keypair
BOOST_AUTO_TEST_CASE(keygen_sign_verify_roundtrip)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(dil.GenerateKeyPair(pk, sk));

    BOOST_CHECK_EQUAL(pk.size(), pqc::Dilithium::PUBLIC_KEY_SIZE);
    BOOST_CHECK_EQUAL(sk.size(), pqc::Dilithium::PRIVATE_KEY_SIZE);

    const std::vector<uint8_t> msg = {'H', 'e', 'l', 'l', 'o', ',', ' ', 'M', 'L', '-', 'D', 'S', 'A'};

    std::vector<uint8_t> sig;
    BOOST_REQUIRE(dil.Sign(msg, sk, sig));
    BOOST_CHECK_EQUAL(sig.size(), pqc::Dilithium::SIGNATURE_SIZE);

    BOOST_CHECK(dil.Verify(msg, sig, pk));
}

// Verify fails when the message has been tampered
BOOST_AUTO_TEST_CASE(verify_fails_tampered_message)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(dil.GenerateKeyPair(pk, sk));

    const std::vector<uint8_t> msg = {0x01, 0x02, 0x03, 0x04};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(dil.Sign(msg, sk, sig));

    std::vector<uint8_t> tampered = msg;
    tampered[0] ^= 0xff;

    BOOST_CHECK(!dil.Verify(tampered, sig, pk));
}

// Verify fails when the signature has been tampered
BOOST_AUTO_TEST_CASE(verify_fails_tampered_signature)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(dil.GenerateKeyPair(pk, sk));

    const std::vector<uint8_t> msg = {0xde, 0xad, 0xbe, 0xef};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(dil.Sign(msg, sk, sig));

    // Flip a byte in the signature
    sig[42] ^= 0x01;

    BOOST_CHECK(!dil.Verify(msg, sig, pk));
}

// Verify fails when the wrong public key is used
BOOST_AUTO_TEST_CASE(verify_fails_wrong_public_key)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> pk1, sk1;
    BOOST_REQUIRE(dil.GenerateKeyPair(pk1, sk1));

    std::vector<uint8_t> pk2, sk2;
    BOOST_REQUIRE(dil.GenerateKeyPair(pk2, sk2));

    const std::vector<uint8_t> msg = {'t', 'e', 's', 't'};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(dil.Sign(msg, sk1, sig));

    // Verify with the correct key succeeds
    BOOST_CHECK(dil.Verify(msg, sig, pk1));
    // Verify with a different key fails
    BOOST_CHECK(!dil.Verify(msg, sig, pk2));
}

// Deterministic key derivation: same 32-byte seed → identical keypair
BOOST_AUTO_TEST_CASE(deterministic_derivation)
{
    pqc::Dilithium dil;

    // 32-byte test seed
    std::vector<uint8_t> seed(32);
    for (int i = 0; i < 32; i++) seed[i] = static_cast<uint8_t>(i);

    std::vector<uint8_t> pk1, sk1;
    BOOST_REQUIRE(dil.DeriveKeyPair(seed, pk1, sk1));

    std::vector<uint8_t> pk2, sk2;
    BOOST_REQUIRE(dil.DeriveKeyPair(seed, pk2, sk2));

    BOOST_CHECK(pk1 == pk2);
    BOOST_CHECK(sk1 == sk2);

    BOOST_CHECK_EQUAL(pk1.size(), pqc::Dilithium::PUBLIC_KEY_SIZE);
    BOOST_CHECK_EQUAL(sk1.size(), pqc::Dilithium::PRIVATE_KEY_SIZE);

    // Signature from derived key verifies
    const std::vector<uint8_t> msg = {0xca, 0xfe, 0xba, 0xbe};
    std::vector<uint8_t> sig;
    BOOST_REQUIRE(dil.Sign(msg, sk1, sig));
    BOOST_CHECK(dil.Verify(msg, sig, pk1));
}

// Different seeds produce different keypairs
BOOST_AUTO_TEST_CASE(different_seeds_different_keys)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> seed1(32, 0x00);
    std::vector<uint8_t> seed2(32, 0xff);

    std::vector<uint8_t> pk1, sk1, pk2, sk2;
    BOOST_REQUIRE(dil.DeriveKeyPair(seed1, pk1, sk1));
    BOOST_REQUIRE(dil.DeriveKeyPair(seed2, pk2, sk2));

    BOOST_CHECK(pk1 != pk2);
    BOOST_CHECK(sk1 != sk2);
}

BOOST_AUTO_TEST_CASE(deterministic_signature_same_key_same_message)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> seed(32);
    for (int i = 0; i < 32; ++i) seed[i] = static_cast<uint8_t>(0xa0 + i);

    std::vector<uint8_t> pk, sk;
    BOOST_REQUIRE(dil.DeriveKeyPair(seed, pk, sk));

    const std::vector<uint8_t> msg = {'Q', 'B', 'T', 'C'};
    std::vector<uint8_t> sig1, sig2;
    BOOST_REQUIRE(dil.Sign(msg, sk, sig1));
    BOOST_REQUIRE(dil.Sign(msg, sk, sig2));

    BOOST_CHECK_EQUAL(sig1.size(), pqc::Dilithium::SIGNATURE_SIZE);
    BOOST_CHECK(sig1 == sig2);
    BOOST_CHECK(dil.Verify(msg, sig1, pk));
}

// DeriveKeyPair rejects a seed shorter than 32 bytes
BOOST_AUTO_TEST_CASE(derive_rejects_short_seed)
{
    pqc::Dilithium dil;

    std::vector<uint8_t> short_seed(16, 0xaa);
    std::vector<uint8_t> pk, sk;
    BOOST_CHECK(!dil.DeriveKeyPair(short_seed, pk, sk));
}

BOOST_AUTO_TEST_SUITE_END()
