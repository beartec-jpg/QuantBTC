#include "pqc_manager.h"
#include <logging.h>

namespace pqc {

PQCManager& PQCManager::GetInstance() {
    static PQCManager instance;
    return instance;
}

bool PQCManager::Initialize(const std::vector<PQCAlgorithm>& algorithms) {
    m_enabledAlgorithms = algorithms;
    
    // Initialize signature algorithm instances if enabled
    for (const auto& algo : algorithms) {
        switch (algo) {
            case PQCAlgorithm::SPHINCS:
                m_sphincs = std::make_unique<SPHINCS>();
                break;
            case PQCAlgorithm::DILITHIUM:
                m_dilithium = std::make_unique<Dilithium>();
                break;
            case PQCAlgorithm::FALCON:
                m_falcon = std::make_unique<Falcon>();
                break;
            case PQCAlgorithm::SQISIGN:
                m_sqisign = std::make_unique<SQIsign>();
                break;
            case PQCAlgorithm::KYBER:
            case PQCAlgorithm::FRODOKEM:
            case PQCAlgorithm::NTRU:
                break;
            default:
                break;
        }
    }
    return true;
}

bool PQCManager::GenerateSignatureKeyPair(PQCAlgorithm algo,
                                        std::vector<unsigned char>& publicKey,
                                        std::vector<unsigned char>& privateKey) {
    try {
        switch (algo) {
            case PQCAlgorithm::SPHINCS:
                if (!m_sphincs) return false;
                return m_sphincs->GenerateKeyPair(publicKey, privateKey);
            
            case PQCAlgorithm::DILITHIUM:
                if (!m_dilithium) return false;
                return m_dilithium->GenerateKeyPair(publicKey, privateKey);
            
            case PQCAlgorithm::FALCON:
                if (!m_falcon) return false;
                return m_falcon->GenerateKeyPair(publicKey, privateKey);
            
            case PQCAlgorithm::SQISIGN:
                if (!m_sqisign) return false;
                return m_sqisign->GenerateKeyPair(publicKey, privateKey);
            
            default:
                LogPrintf("PQCManager::GenerateSignatureKeyPair: Unsupported algorithm\n");
                return false;
        }
    } catch (const std::exception& e) {
        LogPrintf("PQCManager::GenerateSignatureKeyPair: %s\n", e.what());
        return false;
    }
}

bool PQCManager::Sign(PQCAlgorithm algo,
                     const std::vector<unsigned char>& message,
                     const std::vector<unsigned char>& privateKey,
                     std::vector<unsigned char>& signature) {
    try {
        switch (algo) {
            case PQCAlgorithm::SPHINCS:
                if (!m_sphincs) return false;
                return m_sphincs->Sign(message, privateKey, signature);
            
            case PQCAlgorithm::DILITHIUM:
                if (!m_dilithium) return false;
                return m_dilithium->Sign(message, privateKey, signature);
            
            case PQCAlgorithm::FALCON:
                if (!m_falcon) return false;
                return m_falcon->Sign(message, privateKey, signature);
            
            case PQCAlgorithm::SQISIGN:
                if (!m_sqisign) return false;
                return m_sqisign->Sign(message, privateKey, signature);
            
            default:
                LogPrintf("PQCManager::Sign: Unsupported algorithm\n");
                return false;
        }
    } catch (const std::exception& e) {
        LogPrintf("PQCManager::Sign: %s\n", e.what());
        return false;
    }
}

bool PQCManager::Verify(PQCAlgorithm algo,
                       const std::vector<unsigned char>& message,
                       const std::vector<unsigned char>& signature,
                       const std::vector<unsigned char>& publicKey) {
    try {
        switch (algo) {
            case PQCAlgorithm::SPHINCS:
                if (!m_sphincs) return false;
                return m_sphincs->Verify(message, signature, publicKey);
            
            case PQCAlgorithm::DILITHIUM:
                if (!m_dilithium) return false;
                return m_dilithium->Verify(message, signature, publicKey);
            
            case PQCAlgorithm::FALCON:
                if (!m_falcon) return false;
                return m_falcon->Verify(message, signature, publicKey);
            
            case PQCAlgorithm::SQISIGN:
                if (!m_sqisign) return false;
                return m_sqisign->Verify(message, signature, publicKey);
            
            default:
                LogPrintf("PQCManager::Verify: Unsupported algorithm\n");
                return false;
        }
    } catch (const std::exception& e) {
        LogPrintf("PQCManager::Verify: %s\n", e.what());
        return false;
    }
}

bool PQCManager::GenerateHybridKeys(std::vector<unsigned char>& publicKey,
                                  std::vector<unsigned char>& privateKey) {
    // Generate keys for each enabled PQC algorithm
    for (const auto& algo : m_enabledAlgorithms) {
        switch (algo) {
            case PQCAlgorithm::KYBER: {
                unsigned char kyber_pk[KYBER_PUBLIC_KEY_BYTES];
                unsigned char kyber_sk[KYBER_SECRET_KEY_BYTES];
                if (!Kyber::KeyGen(kyber_pk, kyber_sk)) {
                    return false;
                }
                publicKey.insert(publicKey.end(), kyber_pk, kyber_pk + KYBER_PUBLIC_KEY_BYTES);
                privateKey.insert(privateKey.end(), kyber_sk, kyber_sk + KYBER_SECRET_KEY_BYTES);
                break;
            }
            case PQCAlgorithm::FRODOKEM: {
                unsigned char frodo_pk[FRODO_PUBLIC_KEY_BYTES];
                unsigned char frodo_sk[FRODO_SECRET_KEY_BYTES];
                if (!FrodoKEM::KeyGen(frodo_pk, frodo_sk)) {
                    return false;
                }
                publicKey.insert(publicKey.end(), frodo_pk, frodo_pk + FRODO_PUBLIC_KEY_BYTES);
                privateKey.insert(privateKey.end(), frodo_sk, frodo_sk + FRODO_SECRET_KEY_BYTES);
                break;
            }
            case PQCAlgorithm::NTRU: {
                unsigned char ntru_pk[NTRU_PUBLIC_KEY_BYTES];
                unsigned char ntru_sk[NTRU_SECRET_KEY_BYTES];
                if (!NTRU::KeyGen(ntru_pk, ntru_sk)) {
                    return false;
                }
                publicKey.insert(publicKey.end(), ntru_pk, ntru_pk + NTRU_PUBLIC_KEY_BYTES);
                privateKey.insert(privateKey.end(), ntru_sk, ntru_sk + NTRU_SECRET_KEY_BYTES);
                break;
            }
            default:
                break;
        }
    }
    return true;
}

bool PQCManager::HybridEncapsulate(const std::vector<unsigned char>& publicKey,
                                 std::vector<unsigned char>& ciphertext,
                                 std::vector<unsigned char>& sharedSecret) {
    size_t offset = 0;
    std::vector<unsigned char> combinedSecret;

    for (const auto& algo : m_enabledAlgorithms) {
        switch (algo) {
            case PQCAlgorithm::KYBER: {
                unsigned char ct[KYBER_CIPHERTEXT_BYTES];
                unsigned char ss[KYBER_SHARED_SECRET_BYTES];
                if (!Kyber::Encaps(ct, ss, &publicKey[offset])) {
                    return false;
                }
                ciphertext.insert(ciphertext.end(), ct, ct + KYBER_CIPHERTEXT_BYTES);
                combinedSecret.insert(combinedSecret.end(), ss, ss + KYBER_SHARED_SECRET_BYTES);
                offset += KYBER_PUBLIC_KEY_BYTES;
                break;
            }
            // Similar implementations for FRODOKEM and NTRU
            default:
                break;
        }
    }

    // Combine shared secrets using SHA256
    // TODO: Implement proper secret combining function
    sharedSecret = combinedSecret;
    return true;
}

bool PQCManager::HybridDecapsulate(const std::vector<unsigned char>& privateKey,
                                 const std::vector<unsigned char>& ciphertext,
                                 std::vector<unsigned char>& sharedSecret) {
    size_t sk_offset = 0;
    size_t ct_offset = 0;
    std::vector<unsigned char> combinedSecret;

    for (const auto& algo : m_enabledAlgorithms) {
        switch (algo) {
            case PQCAlgorithm::KYBER: {
                unsigned char ss[KYBER_SHARED_SECRET_BYTES];
                if (!Kyber::Decaps(ss, &ciphertext[ct_offset], &privateKey[sk_offset])) {
                    return false;
                }
                combinedSecret.insert(combinedSecret.end(), ss, ss + KYBER_SHARED_SECRET_BYTES);
                sk_offset += KYBER_SECRET_KEY_BYTES;
                ct_offset += KYBER_CIPHERTEXT_BYTES;
                break;
            }
            // Similar implementations for FRODOKEM and NTRU
            default:
                break;
        }
    }

    // Combine shared secrets using SHA256
    // TODO: Implement proper secret combining function
    sharedSecret = combinedSecret;
    return true;
}

} // namespace pqc
