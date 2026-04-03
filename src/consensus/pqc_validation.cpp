#include <consensus/pqc_validation.h>
#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>

namespace Consensus {

// PQC activation height.  Set to 0 so that PQC is active from genesis on all
// QBTC networks.  This matches the BIP9 deployment entry DEPLOYMENT_PQC which
// is set to ALWAYS_ACTIVE on QBTC chains.  On legacy Bitcoin chains
// DEPLOYMENT_PQC is set to NEVER_ACTIVE and this height check is moot.
static const int PQC_ACTIVATION_HEIGHT = 0;

bool IsPQCActivated(int nHeight)
{
    return nHeight >= PQC_ACTIVATION_HEIGHT;
}

bool HasPQCSignatures(const CTransaction& tx) {
    // Detect PQC hybrid witness: [ECDSA sig, pubkey, PQC sig, PQC pubkey]
    // sign.cpp produces witness v0 transactions with a 4-element stack.
    for (const auto& input : tx.vin) {
        if (!input.scriptWitness.IsNull() && input.scriptWitness.stack.size() == 4) {
            const auto& pqc_sig = input.scriptWitness.stack[2];
            const auto& pqc_pubkey = input.scriptWitness.stack[3];
            // Dilithium: sig=2420, pubkey=1312
            if (pqc_sig.size() == pqc::Dilithium::SIGNATURE_SIZE &&
                pqc_pubkey.size() == pqc::Dilithium::PUBLIC_KEY_SIZE) {
                return true;
            }
            // SPHINCS+: sig<=17088, pubkey=32
            if (!pqc_sig.empty() && pqc_sig.size() <= pqc::SPHINCS::SIGNATURE_SIZE &&
                pqc_pubkey.size() == pqc::SPHINCS::PUBLIC_KEY_SIZE) {
                return true;
            }
        }
    }
    return false;
}

} // namespace Consensus
