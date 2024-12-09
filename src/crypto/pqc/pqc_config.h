#ifndef BITCOIN_CRYPTO_PQC_CONFIG_H
#define BITCOIN_CRYPTO_PQC_CONFIG_H

#include <string>
#include <vector>

namespace pqc {

enum class PQCSignatureScheme {
    DILITHIUM,
    FALCON,
    SPHINCS_PLUS
};

struct PQCConfig {
    bool enable_pqc{true};
    bool enable_hybrid_keys{true};
    bool enable_hybrid_signatures{true};
    std::vector<PQCAlgorithm> enabled_kems{
        PQCAlgorithm::KYBER,
        PQCAlgorithm::FRODOKEM,
        PQCAlgorithm::NTRU
    };
    std::vector<PQCSignatureScheme> enabled_signatures{
        PQCSignatureScheme::DILITHIUM,
        PQCSignatureScheme::FALCON
    };
    
    static PQCConfig& GetInstance() {
        static PQCConfig instance;
        return instance;
    }
    
    void LoadFromArgs(const std::vector<std::string>& args);
private:
    PQCConfig() = default;
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_CONFIG_H
