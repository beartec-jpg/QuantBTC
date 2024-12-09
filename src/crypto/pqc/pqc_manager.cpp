#include "pqc_manager.h"
#include "../random.h"
#include <algorithm>

namespace pqc {

PQCManager& PQCManager::GetInstance() {
    static PQCManager instance;
    return instance;
}

bool PQCManager::Initialize(const std::vector<PQCAlgorithm>& algorithms) {
    if (algorithms.empty()) {
        return false;
    }
    m_enabledAlgorithms = algorithms;
    return true;
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
        }
    }

    // Combine shared secrets using SHA256
    // TODO: Implement proper secret combining function
    sharedSecret = combinedSecret;
    return true;
}

} // namespace pqc
