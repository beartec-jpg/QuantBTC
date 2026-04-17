#include "pqc_config.h"
#include <logging.h>

namespace pqc {

void PQCConfig::LoadFromArgs(const std::vector<std::string>& args) {
    for (const std::string& arg : args) {
        if (arg == "-pqc=0") {
            enable_pqc = false;
        }
        else if (arg == "-pqc=1") {
            enable_pqc = true;
        }
        else if (arg == "-pqchybridkeys=0") {
            enable_hybrid_keys = false;
        }
        else if (arg == "-pqchybridkeys=1") {
            enable_hybrid_keys = true;
        }
        else if (arg == "-pqchybridsig=0") {
            enable_hybrid_signatures = false;
        }
        else if (arg == "-pqchybridsig=1") {
            enable_hybrid_signatures = true;
        }
        else if (arg.rfind("-pqcalgo=", 0) == 0) {
            std::string algoList = arg.substr(9);
            enabled_kems.clear();

            const auto handle_kem = [&](const std::string& algo) {
                if (algo.empty()) return;
                if (algo == "kyber") {
                    LogPrintf("PQC WARNING: kyber KEM is currently stubbed/disabled, ignoring explicit request\n");
                } else if (algo == "frodo") {
                    LogPrintf("PQC WARNING: frodo KEM is currently stubbed/disabled, ignoring explicit request\n");
                } else if (algo == "ntru") {
                    LogPrintf("PQC WARNING: ntru KEM is currently stubbed/disabled, ignoring explicit request\n");
                } else {
                    LogPrintf("PQC WARNING: unknown pqcalgo '%s', ignoring\n", algo);
                }
            };

            size_t pos = 0;
            while ((pos = algoList.find(',')) != std::string::npos) {
                handle_kem(algoList.substr(0, pos));
                algoList.erase(0, pos + 1);
            }

            // Handle last algorithm
            handle_kem(algoList);
        }
        else if (arg.rfind("-pqcsig=", 0) == 0) {
            std::string sigList = arg.substr(8);
            enabled_signatures.clear();

            size_t pos = 0;
            bool saw_falcon = false;
            while ((pos = sigList.find(',')) != std::string::npos) {
                std::string sig = sigList.substr(0, pos);
                if (sig == "falcon") {
                    saw_falcon = true;
                } else if (!sig.empty()) {
                    LogPrintf("PQC WARNING: signature scheme '%s' is not permitted by policy (only 'falcon' is accepted), ignoring\n", sig);
                }
                sigList.erase(0, pos + 1);
            }

            // Handle last signature scheme
            if (sigList == "falcon") {
                saw_falcon = true;
            } else if (!sigList.empty()) {
                LogPrintf("PQC WARNING: signature scheme '%s' is not permitted by policy (only 'falcon' is accepted), ignoring\n", sigList);
            }

            if (!saw_falcon) {
                LogPrintf("PQC WARNING: no permitted -pqcsig value provided; forcing falcon\n");
            }
            enabled_signatures.push_back(PQCSignatureScheme::FALCON);
            preferred_sig_scheme = PQCSignatureScheme::FALCON;
        }
    }
}

} // namespace pqc
