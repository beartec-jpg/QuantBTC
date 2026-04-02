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
            
            size_t pos = 0;
            while ((pos = algoList.find(',')) != std::string::npos) {
                std::string algo = algoList.substr(0, pos);
                if (algo == "kyber") {
                    enabled_kems.push_back(PQCAlgorithm::KYBER);
                }
                else if (algo == "frodo") {
                    enabled_kems.push_back(PQCAlgorithm::FRODOKEM);
                }
                else if (algo == "ntru") {
                    enabled_kems.push_back(PQCAlgorithm::NTRU);
                }
                algoList.erase(0, pos + 1);
            }
            
            // Handle last algorithm
            if (algoList == "kyber") {
                enabled_kems.push_back(PQCAlgorithm::KYBER);
            }
            else if (algoList == "frodo") {
                enabled_kems.push_back(PQCAlgorithm::FRODOKEM);
            }
            else if (algoList == "ntru") {
                enabled_kems.push_back(PQCAlgorithm::NTRU);
            }
        }
        else if (arg.rfind("-pqcsig=", 0) == 0) {
            std::string sigList = arg.substr(8);
            enabled_signatures.clear();
            
            size_t pos = 0;
            while ((pos = sigList.find(',')) != std::string::npos) {
                std::string sig = sigList.substr(0, pos);
                if (sig == "dilithium") {
                    enabled_signatures.push_back(PQCSignatureScheme::DILITHIUM);
                }
                else if (sig == "sphincs") {
                    enabled_signatures.push_back(PQCSignatureScheme::SPHINCS_PLUS);
                }
                else if (sig == "falcon") {
                    LogPrintf("PQC WARNING: falcon signature scheme is not yet implemented, ignoring\n");
                }
                else if (sig == "sqisign") {
                    LogPrintf("PQC WARNING: sqisign signature scheme is not yet implemented, ignoring\n");
                }
                sigList.erase(0, pos + 1);
            }
            
            // Handle last signature scheme
            if (sigList == "dilithium") {
                enabled_signatures.push_back(PQCSignatureScheme::DILITHIUM);
            }
            else if (sigList == "sphincs") {
                enabled_signatures.push_back(PQCSignatureScheme::SPHINCS_PLUS);
            }
            else if (sigList == "falcon") {
                LogPrintf("PQC WARNING: falcon signature scheme is not yet implemented, ignoring\n");
            }
            else if (sigList == "sqisign") {
                LogPrintf("PQC WARNING: sqisign signature scheme is not yet implemented, ignoring\n");
            }
        }
    }
}

} // namespace pqc
