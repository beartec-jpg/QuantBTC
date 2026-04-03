#include <boost/test/unit_test.hpp>
#include <crypto/pqc/pqc_manager.h>
#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>
#include <vector>

BOOST_AUTO_TEST_SUITE(pqc_signature_tests)

/**
 * Test a fully implemented PQC signature algorithm for round-trip correctness.
 * Checks key generation, signing, verification, and tamper detection,
 * as well as expected key/signature sizes.
 */
void TestImplementedSignatureAlgorithm(pqc::PQCAlgorithm algo,
                                       size_t expectedPkSize,
                                       size_t expectedSkSize,
                                       size_t expectedSigSize) {
    pqc::PQCManager& manager = pqc::PQCManager::GetInstance();

    // Initialize PQC system with the algorithm
    std::vector<pqc::PQCAlgorithm> algorithms = {algo};
    BOOST_CHECK(manager.Initialize(algorithms));

    // Generate key pair
    std::vector<unsigned char> publicKey, privateKey;
    BOOST_CHECK(manager.GenerateSignatureKeyPair(algo, publicKey, privateKey));

    // Verify key sizes match expected values
    BOOST_CHECK_EQUAL(publicKey.size(), expectedPkSize);
    BOOST_CHECK_EQUAL(privateKey.size(), expectedSkSize);

    // Keys must not be all-zero (real crypto output)
    bool pkAllZero = std::all_of(publicKey.begin(), publicKey.end(), [](unsigned char c){ return c == 0; });
    BOOST_CHECK(!pkAllZero);

    // Test message
    std::vector<unsigned char> message = {'T', 'e', 's', 't', ' ', 'm', 'e', 's', 's', 'a', 'g', 'e'};

    // Sign message
    std::vector<unsigned char> signature;
    BOOST_CHECK(manager.Sign(algo, message, privateKey, signature));

    // Verify signature size matches expected value
    BOOST_CHECK_EQUAL(signature.size(), expectedSigSize);

    // Verify signature
    BOOST_CHECK(manager.Verify(algo, message, signature, publicKey));

    // Verify signature fails with modified message (tamper detection)
    std::vector<unsigned char> modified_message = message;
    modified_message[0] = 'M';
    BOOST_CHECK(!manager.Verify(algo, modified_message, signature, publicKey));

    // Verify signature fails with corrupted signature
    std::vector<unsigned char> corrupted_sig = signature;
    corrupted_sig[0] ^= 0xff;
    BOOST_CHECK(!manager.Verify(algo, message, corrupted_sig, publicKey));
}

/**
 * Test that an unimplemented (stub) algorithm correctly rejects all operations.
 */
void TestUnimplementedSignatureAlgorithm(pqc::PQCAlgorithm algo) {
    pqc::PQCManager& manager = pqc::PQCManager::GetInstance();

    std::vector<pqc::PQCAlgorithm> algorithms = {algo};
    BOOST_CHECK(manager.Initialize(algorithms));

    // Key generation must fail for unimplemented algorithms
    std::vector<unsigned char> publicKey, privateKey;
    BOOST_CHECK(!manager.GenerateSignatureKeyPair(algo, publicKey, privateKey));

    // Signing must fail for unimplemented algorithms
    std::vector<unsigned char> message = {'T', 'e', 's', 't'};
    std::vector<unsigned char> dummyKey(64, 0x42);
    std::vector<unsigned char> signature;
    BOOST_CHECK(!manager.Sign(algo, message, dummyKey, signature));

    // Verification must fail for unimplemented algorithms
    std::vector<unsigned char> dummySig(128, 0x42);
    BOOST_CHECK(!manager.Verify(algo, message, dummySig, dummyKey));
}

BOOST_AUTO_TEST_CASE(sphincs_signature_test)
{
    TestImplementedSignatureAlgorithm(pqc::PQCAlgorithm::SPHINCS,
                                     pqc::SPHINCS::PUBLIC_KEY_SIZE,
                                     pqc::SPHINCS::PRIVATE_KEY_SIZE,
                                     pqc::SPHINCS::SIGNATURE_SIZE);
}

BOOST_AUTO_TEST_CASE(dilithium_signature_test)
{
    TestImplementedSignatureAlgorithm(pqc::PQCAlgorithm::DILITHIUM,
                                     pqc::Dilithium::PUBLIC_KEY_SIZE,
                                     pqc::Dilithium::PRIVATE_KEY_SIZE,
                                     pqc::Dilithium::SIGNATURE_SIZE);
}

BOOST_AUTO_TEST_CASE(falcon_signature_test)
{
    // Falcon is NOT IMPLEMENTED — all operations must be rejected
    TestUnimplementedSignatureAlgorithm(pqc::PQCAlgorithm::FALCON);
}

BOOST_AUTO_TEST_CASE(sqisign_signature_test)
{
    // SQIsign is NOT IMPLEMENTED — all operations must be rejected
    TestUnimplementedSignatureAlgorithm(pqc::PQCAlgorithm::SQISIGN);
}

BOOST_AUTO_TEST_SUITE_END()
