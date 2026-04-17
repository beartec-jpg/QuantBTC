#ifndef BITCOIN_CRYPTO_PQC_CONFIG_H
#define BITCOIN_CRYPTO_PQC_CONFIG_H

#include "pqc_manager.h"

#include <optional>
#include <string>
#include <vector>

namespace pqc {

enum class PQCSignatureScheme {
    DILITHIUM,
    FALCON,
    FALCON1024,
    SPHINCS_PLUS
};

enum class PQCMode {
    HYBRID,     // ECDSA + Dilithium (default)
    CLASSICAL,  // ECDSA only (PQC disabled)
    PURE        // Dilithium only (future, not yet supported at consensus)
};

struct PQCConfig {
    bool enable_pqc{false};
    bool enable_hybrid_keys{true};
    bool enable_hybrid_signatures{false};
    PQCMode pqc_mode{PQCMode::HYBRID};
    // Keep broken/experimental PQC algorithms disabled by default until they are hardened.
    std::vector<PQCAlgorithm> enabled_kems{};
    std::vector<PQCSignatureScheme> enabled_signatures{};
    PQCSignatureScheme preferred_sig_scheme{PQCSignatureScheme::FALCON};
    
    static PQCConfig& GetInstance() {
        static PQCConfig instance;
        return instance;
    }

    /** Thread-local per-transaction override for PQC signing.
     *  When set, takes precedence over enable_hybrid_signatures. */
    static std::optional<bool>& SigningOverride() {
        static thread_local std::optional<bool> override;
        return override;
    }

    /** Check whether PQC signing should occur, respecting per-tx overrides. */
    bool ShouldSignPQC() const {
        auto& ovr = SigningOverride();
        if (ovr.has_value()) return *ovr;
        return enable_hybrid_signatures;
    }

    void LoadFromArgs(const std::vector<std::string>& args);
private:
    PQCConfig() = default;
};

/** RAII guard: temporarily override PQC signing for the current thread.
 *  Used by wallet RPCs to control per-transaction hybrid vs classical signing. */
class PQCSigningOverride {
    std::optional<bool> m_saved;
public:
    explicit PQCSigningOverride(std::optional<bool> use_pqc)
        : m_saved(PQCConfig::SigningOverride())
    {
        if (use_pqc.has_value()) PQCConfig::SigningOverride() = use_pqc;
    }
    ~PQCSigningOverride() { PQCConfig::SigningOverride() = m_saved; }
    PQCSigningOverride(const PQCSigningOverride&) = delete;
    PQCSigningOverride& operator=(const PQCSigningOverride&) = delete;
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_CONFIG_H
