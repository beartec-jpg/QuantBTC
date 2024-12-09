#ifndef BITCOIN_CRYPTO_PQC_MANAGER_H
#define BITCOIN_CRYPTO_PQC_MANAGER_H

#include "kyber.h"
#include "frodokem.h"
#include "ntru.h"
#include <vector>
#include <memory>

namespace pqc {

enum class PQCAlgorithm {
    KYBER,
    FRODOKEM,
    NTRU
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

private:
    PQCManager() = default;
    ~PQCManager() = default;
    PQCManager(const PQCManager&) = delete;
    PQCManager& operator=(const PQCManager&) = delete;

    std::vector<PQCAlgorithm> m_enabledAlgorithms;
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_MANAGER_H
