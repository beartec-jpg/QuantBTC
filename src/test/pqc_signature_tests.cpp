#include <boost/test/unit_test.hpp>
#include <crypto/pqc/pqc_manager.h>
#include <vector>

BOOST_AUTO_TEST_SUITE(pqc_signature_tests)

void TestSignatureAlgorithm(pqc::PQCAlgorithm algo) {
    pqc::PQCManager& manager = pqc::PQCManager::GetInstance();
    
    // Initialize PQC system with the algorithm
    std::vector<pqc::PQCAlgorithm> algorithms = {algo};
    BOOST_CHECK(manager.Initialize(algorithms));
    
    // Generate key pair
    std::vector<unsigned char> publicKey, privateKey;
    BOOST_CHECK(manager.GenerateSignatureKeyPair(algo, publicKey, privateKey));
    
    // Test message
    std::vector<unsigned char> message = {'T', 'e', 's', 't', ' ', 'm', 'e', 's', 's', 'a', 'g', 'e'};
    
    // Sign message
    std::vector<unsigned char> signature;
    BOOST_CHECK(manager.Sign(algo, message, privateKey, signature));
    
    // Verify signature
    BOOST_CHECK(manager.Verify(algo, message, signature, publicKey));
    
    // Verify signature fails with modified message
    std::vector<unsigned char> modified_message = message;
    modified_message[0] = 'M';
    BOOST_CHECK(!manager.Verify(algo, modified_message, signature, publicKey));
}

BOOST_AUTO_TEST_CASE(sphincs_signature_test)
{
    TestSignatureAlgorithm(pqc::PQCAlgorithm::SPHINCS);
}

BOOST_AUTO_TEST_CASE(dilithium_signature_test)
{
    TestSignatureAlgorithm(pqc::PQCAlgorithm::DILITHIUM);
}

BOOST_AUTO_TEST_CASE(falcon_signature_test)
{
    TestSignatureAlgorithm(pqc::PQCAlgorithm::FALCON);
}

BOOST_AUTO_TEST_CASE(sqisign_signature_test)
{
    TestSignatureAlgorithm(pqc::PQCAlgorithm::SQISIGN);
}

BOOST_AUTO_TEST_SUITE_END()
