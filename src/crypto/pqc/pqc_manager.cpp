#include "pqc_manager.h"
#include "dilithium.h"
#include "falcon.h"
#include "sphincs.h"
#include <crypto/hkdf_sha256_32.h>
#include <logging.h>
#include <support/cleanse.h>

namespace pqc {

PQCManager& PQCManager::GetInstance() {
    static PQCManager instance;
    return instance;
}

bool PQCManager::Initialize(const std::vector<PQCAlgorithm>& algorithms) {
    m_enabledAlgorithms = algorithms;
    return true;
}

bool PQCManager::GenerateSignatureKeyPair(PQCAlgorithm algo,
                                        std::vector<unsigned char>& publicKey,
                                        std::vector<unsigned char>& privateKey) {
    switch (algo) {
        case PQCAlgorithm::DILITHIUM: {
            Dilithium dil;
            return dil.GenerateKeyPair(publicKey, privateKey);
        }
        case PQCAlgorithm::FALCON: {
            Falcon fal;
            return fal.GenerateKeyPair(publicKey, privateKey);
        }
        case PQCAlgorithm::FALCON1024: {
            Falcon1024 fal1024;
            return fal1024.GenerateKeyPair(publicKey, privateKey);
        }
        case PQCAlgorithm::SPHINCS: {
            SPHINCS sph;
            return sph.GenerateKeyPair(publicKey, privateKey);
        }
        case PQCAlgorithm::SQISIGN:
            LogPrintf("PQCManager::GenerateSignatureKeyPair: SQIsign not supported (no NIST standard)\n");
            return false;
        default:
            LogPrintf("PQCManager::GenerateSignatureKeyPair: Unsupported algorithm\n");
            return false;
    }
}

bool PQCManager::Sign(PQCAlgorithm algo,
                     const std::vector<unsigned char>& message,
                     const std::vector<unsigned char>& privateKey,
                     std::vector<unsigned char>& signature) {
    switch (algo) {
        case PQCAlgorithm::DILITHIUM: {
            Dilithium dil;
            return dil.Sign(message, privateKey, signature);
        }
        case PQCAlgorithm::FALCON: {
            Falcon fal;
            return fal.Sign(message, privateKey, signature);
        }
        case PQCAlgorithm::FALCON1024: {
            Falcon1024 fal1024;
            return fal1024.Sign(message, privateKey, signature);
        }
        case PQCAlgorithm::SPHINCS: {
            SPHINCS sph;
            return sph.Sign(message, privateKey, signature);
        }
        case PQCAlgorithm::SQISIGN:
            LogPrintf("PQCManager::Sign: SQIsign not supported\n");
            return false;
        default:
            LogPrintf("PQCManager::Sign: Unsupported algorithm\n");
            return false;
    }
}

bool PQCManager::Verify(PQCAlgorithm algo,
                       const std::vector<unsigned char>& message,
                       const std::vector<unsigned char>& signature,
                       const std::vector<unsigned char>& publicKey) {
    switch (algo) {
        case PQCAlgorithm::DILITHIUM: {
            Dilithium dil;
            return dil.Verify(message, signature, publicKey);
        }
        case PQCAlgorithm::FALCON: {
            Falcon fal;
            return fal.Verify(message, signature, publicKey);
        }
        case PQCAlgorithm::FALCON1024: {
            Falcon1024 fal1024;
            return fal1024.Verify(message, signature, publicKey);
        }
        case PQCAlgorithm::SPHINCS: {
            SPHINCS sph;
            return sph.Verify(message, signature, publicKey);
        }
        case PQCAlgorithm::SQISIGN:
            LogPrintf("PQCManager::Verify: SQIsign not supported\n");
            return false;
        default:
            LogPrintf("PQCManager::Verify: Unsupported algorithm\n");
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
    if (m_enabledAlgorithms.empty()) {
        LogPrintf("PQCManager::HybridEncapsulate: no KEM algorithms enabled; cannot encapsulate\n");
        return false;
    }
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
            case PQCAlgorithm::FRODOKEM: {
                unsigned char ct[FRODO_CIPHERTEXT_BYTES];
                unsigned char ss[FRODO_SHARED_SECRET_BYTES];
                if (!FrodoKEM::Encaps(ct, ss, &publicKey[offset])) {
                    return false;
                }
                ciphertext.insert(ciphertext.end(), ct, ct + FRODO_CIPHERTEXT_BYTES);
                combinedSecret.insert(combinedSecret.end(), ss, ss + FRODO_SHARED_SECRET_BYTES);
                offset += FRODO_PUBLIC_KEY_BYTES;
                break;
            }
            case PQCAlgorithm::NTRU: {
                unsigned char ct[NTRU_CIPHERTEXT_BYTES];
                unsigned char ss[NTRU_SHARED_SECRET_BYTES];
                if (!NTRU::Encaps(ct, ss, &publicKey[offset])) {
                    return false;
                }
                ciphertext.insert(ciphertext.end(), ct, ct + NTRU_CIPHERTEXT_BYTES);
                combinedSecret.insert(combinedSecret.end(), ss, ss + NTRU_SHARED_SECRET_BYTES);
                offset += NTRU_PUBLIC_KEY_BYTES;
                break;
            }
            default:
                break;
        }
    }

    // Combine shared secrets using HKDF-SHA256 (RFC 5869) with domain separation
    sharedSecret.resize(32);
    CHKDF_HMAC_SHA256_L32 hkdf(combinedSecret.data(), combinedSecret.size(),
                               "QuantBTC-HybridKEM-Salt");
    hkdf.Expand32("QuantBTC-HybridKEM-v1", sharedSecret.data());
    memory_cleanse(combinedSecret.data(), combinedSecret.size());
    return true;
}

bool PQCManager::HybridDecapsulate(const std::vector<unsigned char>& privateKey,
                                 const std::vector<unsigned char>& ciphertext,
                                 std::vector<unsigned char>& sharedSecret) {
    if (m_enabledAlgorithms.empty()) {
        LogPrintf("PQCManager::HybridDecapsulate: no KEM algorithms enabled; cannot decapsulate\n");
        return false;
    }
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
            case PQCAlgorithm::FRODOKEM: {
                unsigned char ss[FRODO_SHARED_SECRET_BYTES];
                if (!FrodoKEM::Decaps(ss, &ciphertext[ct_offset], &privateKey[sk_offset])) {
                    return false;
                }
                combinedSecret.insert(combinedSecret.end(), ss, ss + FRODO_SHARED_SECRET_BYTES);
                sk_offset += FRODO_SECRET_KEY_BYTES;
                ct_offset += FRODO_CIPHERTEXT_BYTES;
                break;
            }
            case PQCAlgorithm::NTRU: {
                unsigned char ss[NTRU_SHARED_SECRET_BYTES];
                if (!NTRU::Decaps(ss, &ciphertext[ct_offset], &privateKey[sk_offset])) {
                    return false;
                }
                combinedSecret.insert(combinedSecret.end(), ss, ss + NTRU_SHARED_SECRET_BYTES);
                sk_offset += NTRU_SECRET_KEY_BYTES;
                ct_offset += NTRU_CIPHERTEXT_BYTES;
                break;
            }
            default:
                break;
        }
    }

    // Combine shared secrets using HKDF-SHA256 (RFC 5869) with domain separation
    sharedSecret.resize(32);
    CHKDF_HMAC_SHA256_L32 hkdf(combinedSecret.data(), combinedSecret.size(),
                               "QuantBTC-HybridKEM-Salt");
    hkdf.Expand32("QuantBTC-HybridKEM-v1", sharedSecret.data());
    memory_cleanse(combinedSecret.data(), combinedSecret.size());
    return true;
}

} // namespace pqc
