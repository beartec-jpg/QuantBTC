#include <boost/test/unit_test.hpp>

#include <crypto/pqc/kyber.h>
#include <crypto/pqc/frodokem.h>
#include <crypto/pqc/ntru.h>
#include <crypto/pqc/pqc_manager.h>

BOOST_AUTO_TEST_SUITE(pqc_tests)

BOOST_AUTO_TEST_CASE(kyber_basic)
{
    unsigned char pk[KYBER_PUBLIC_KEY_BYTES];
    unsigned char sk[KYBER_SECRET_KEY_BYTES];
    unsigned char ct[KYBER_CIPHERTEXT_BYTES];
    unsigned char ss1[KYBER_SHARED_SECRET_BYTES];
    unsigned char ss2[KYBER_SHARED_SECRET_BYTES];

    // Test key generation
    BOOST_CHECK(pqc::Kyber::KeyGen(pk, sk));

    // Test encapsulation
    BOOST_CHECK(pqc::Kyber::Encaps(ct, ss1, pk));

    // Test decapsulation
    BOOST_CHECK(pqc::Kyber::Decaps(ss2, ct, sk));

    // Verify shared secrets match
    BOOST_CHECK_EQUAL(memcmp(ss1, ss2, KYBER_SHARED_SECRET_BYTES), 0);
}

BOOST_AUTO_TEST_CASE(pqc_manager_basic)
{
    pqc::PQCManager& manager = pqc::PQCManager::GetInstance();
    std::vector<pqc::PQCAlgorithm> algorithms = {
        pqc::PQCAlgorithm::KYBER,
        pqc::PQCAlgorithm::FRODOKEM,
        pqc::PQCAlgorithm::NTRU
    };

    // Initialize PQC system
    BOOST_CHECK(manager.Initialize(algorithms));

    // Test hybrid key generation
    std::vector<unsigned char> publicKey, privateKey;
    BOOST_CHECK(manager.GenerateHybridKeys(publicKey, privateKey));

    // Test hybrid encapsulation
    std::vector<unsigned char> ciphertext, sharedSecret1;
    BOOST_CHECK(manager.HybridEncapsulate(publicKey, ciphertext, sharedSecret1));

    // Test hybrid decapsulation
    std::vector<unsigned char> sharedSecret2;
    BOOST_CHECK(manager.HybridDecapsulate(privateKey, ciphertext, sharedSecret2));

    // Verify shared secrets match
    BOOST_CHECK_EQUAL(sharedSecret1.size(), sharedSecret2.size());
    BOOST_CHECK_EQUAL(memcmp(sharedSecret1.data(), sharedSecret2.data(), sharedSecret1.size()), 0);
}

BOOST_AUTO_TEST_SUITE_END()
