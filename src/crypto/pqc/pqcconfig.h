#ifndef BITCOIN_CRYPTO_PQC_PQCCONFIG_H
#define BITCOIN_CRYPTO_PQC_PQCCONFIG_H

namespace pqc {

class PQCConfig {
private:
    PQCConfig() = default;
    PQCConfig(const PQCConfig&) = delete;
    PQCConfig& operator=(const PQCConfig&) = delete;

public:
    static PQCConfig& GetInstance() {
        static PQCConfig instance;
        return instance;
    }

    bool enable_hybrid_signatures = true;  // Enable by default
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_PQCCONFIG_H
