#ifndef BITCOIN_CRYPTO_PQC_MANAGER_H
#define BITCOIN_CRYPTO_PQC_MANAGER_H

#include "kyber.h"
#include "frodokem.h"
#include "ntru.h"
#include "sphincs.h"
#include "dilithium.h"
#include "falcon.h"
#include "sqisign.h"
#include <vector>
#include <memory>

namespace pqc {

enum class PQCAlgorithm {
    // Key Encapsulation Mechanisms (KEM)
    KYBER,
    FRODOKEM,
    NTRU,
    // Digital Signature Algorithms
    SPHINCS,
    DILITHIUM,
    FALCON,
    SQISIGN
};

class PQCManager {
public:
    static PQCManager& GetInstance();

    // Initialize PQC system with specific algorithms
    bool Initialize(const std::vector<PQCAlgorithm>& algorithms);

    // Generate hybrid keys (classical + PQC)
    bool GenerateHybridKeys(std::vector<unsigned char>& publicKey,
                           std::vector<unsigned char>& privateKey);

    // Encapsulate key using hybrid encryption
    bool HybridEncapsulate(const std::vector<unsigned char>& publicKey,
                          std::vector<unsigned char>& ciphertext,
                          std::vector<unsigned char>& sharedSecret);

    // Decapsulate key using hybrid encryption
    bool HybridDecapsulate(const std::vector<unsigned char>& privateKey,
                          const std::vector<unsigned char>& ciphertext,
                          std::vector<unsigned char>& sharedSecret);

    // Digital signature methods
    bool GenerateSignatureKeyPair(PQCAlgorithm algo,
                                 std::vector<unsigned char>& publicKey,
                                 std::vector<unsigned char>& privateKey);

    bool Sign(PQCAlgorithm algo,
             const std::vector<unsigned char>& message,
             const std::vector<unsigned char>& privateKey,
             std::vector<unsigned char>& signature);

    bool Verify(PQCAlgorithm algo,
               const std::vector<unsigned char>& message,
               const std::vector<unsigned char>& signature,
               const std::vector<unsigned char>& publicKey);

private:
    PQCManager() = default;
    ~PQCManager() = default;
    PQCManager(const PQCManager&) = delete;
    PQCManager& operator=(const PQCManager&) = delete;

    std::vector<PQCAlgorithm> m_enabledAlgorithms;
    
    // Algorithm instances
    std::unique_ptr<SPHINCS> m_sphincs;
    std::unique_ptr<Dilithium> m_dilithium;
    std::unique_ptr<Falcon> m_falcon;
    std::unique_ptr<SQIsign> m_sqisign;
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_MANAGER_H
