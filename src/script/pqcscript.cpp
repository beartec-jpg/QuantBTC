#include <script/pqcscript.h>
#include <crypto/sha256.h>
#include <hash.h>

PQCScriptHash::PQCScriptHash(const CScript& in) {
    CSHA256().Write(in.data(), in.size()).Finalize(begin());
}

std::string GetPQCTxnOutputType(PQCTxoutType t)
{
    switch (t) {
    case PQCTxoutType::NONSTANDARD: return "pqc_nonstandard";
    case PQCTxoutType::PQC_PUBKEY: return "pqc_pubkey";
    case PQCTxoutType::PQC_PUBKEYHASH: return "pqc_pubkeyhash";
    case PQCTxoutType::PQC_SCRIPTHASH: return "pqc_scripthash";
    case PQCTxoutType::PQC_MULTISIG: return "pqc_multisig";
    case PQCTxoutType::PQC_NULL_DATA: return "pqc_nulldata";
    case PQCTxoutType::PQC_WITNESS_V0: return "pqc_witness_v0";
    } // no default case, so the compiler can warn about missing cases
    return "pqc_unknown";
}

CScript GetScriptForPQCDestination(const PQCPubKeyHash& dest)
{
    return CScript() << OP_DUP << OP_HASH256 << ToByteVector(dest) << OP_EQUALVERIFY << OP_CHECKSIG;
}

CScript GetScriptForPQCPubKey(const std::vector<unsigned char>& pubkey)
{
    return CScript() << pubkey << OP_CHECKSIG;
}

CScript GetScriptForPQCMultisig(int nRequired, const std::vector<std::vector<unsigned char>>& keys)
{
    CScript script;
    script << CScript::EncodeOP_N(nRequired);
    for (const auto& key : keys)
        script << key;
    script << CScript::EncodeOP_N(keys.size()) << OP_CHECKMULTISIG;
    return script;
}

bool ExtractPQCDestination(const CScript& scriptPubKey, PQCPubKeyHash& addressRet)
{
    std::vector<std::vector<unsigned char>> vSolutions;
    PQCTxoutType whichType = SolvePQC(scriptPubKey, vSolutions);

    if (whichType == PQCTxoutType::PQC_PUBKEYHASH) {
        addressRet = PQCPubKeyHash(uint256(vSolutions[0]));
        return true;
    }
    return false;
}

PQCTxoutType SolvePQC(const CScript& scriptPubKey, std::vector<std::vector<unsigned char>>& vSolutionsRet)
{
    vSolutionsRet.clear();

    // PQC Pay-to-pubkey-hash
    if (scriptPubKey.IsPayToPubkeyHash256()) {
        std::vector<unsigned char> hashBytes(scriptPubKey.begin()+3, scriptPubKey.begin()+35);
        vSolutionsRet.push_back(hashBytes);
        return PQCTxoutType::PQC_PUBKEYHASH;
    }

    // PQC Pay-to-script-hash
    if (scriptPubKey.IsPayToScriptHash256()) {
        std::vector<unsigned char> hashBytes(scriptPubKey.begin()+2, scriptPubKey.begin()+34);
        vSolutionsRet.push_back(hashBytes);
        return PQCTxoutType::PQC_SCRIPTHASH;
    }

    // PQC Pay-to-pubkey
    std::vector<unsigned char> data;
    if (scriptPubKey.IsPushOnly() && scriptPubKey.size() > 2) {
        vSolutionsRet.push_back(std::vector<unsigned char>(scriptPubKey.begin()+1, scriptPubKey.end()-1));
        return PQCTxoutType::PQC_PUBKEY;
    }

    vSolutionsRet.clear();
    return PQCTxoutType::NONSTANDARD;
}
