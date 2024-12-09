#include "pqc_config.h"
#include <util/system.h>

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
        else if (arg.substr(0, 9) == "-pqcalgo=") {
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
        else if (arg.substr(0, 9) == "-pqcsig=") {
            std::string sigList = arg.substr(9);
            enabled_signatures.clear();
            
            size_t pos = 0;
            while ((pos = sigList.find(',')) != std::string::npos) {
                std::string sig = sigList.substr(0, pos);
                if (sig == "dilithium") {
                    enabled_signatures.push_back(PQCSignatureScheme::DILITHIUM);
                }
                else if (sig == "falcon") {
                    enabled_signatures.push_back(PQCSignatureScheme::FALCON);
                }
                else if (sig == "sphincs") {
                    enabled_signatures.push_back(PQCSignatureScheme::SPHINCS_PLUS);
                }
                sigList.erase(0, pos + 1);
            }
            
            // Handle last signature scheme
            if (sigList == "dilithium") {
                enabled_signatures.push_back(PQCSignatureScheme::DILITHIUM);
            }
            else if (sigList == "falcon") {
                enabled_signatures.push_back(PQCSignatureScheme::FALCON);
            }
            else if (sigList == "sphincs") {
                enabled_signatures.push_back(PQCSignatureScheme::SPHINCS_PLUS);
            }
        }
    }
}

} // namespace pqc
