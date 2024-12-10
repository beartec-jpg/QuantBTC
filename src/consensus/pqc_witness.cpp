#include <consensus/pqc_witness.h>
#include <hash.h>
#include <script/standard.h>
#include <bech32.h>
#include <util/strencodings.h>

namespace pqc {

size_t PQCWitness::GetVirtualSize() const {
    size_t weight = 0;
    // Calculate weight similar to SegWit
    for (const auto& item : stack) {
        weight += GetSerializeSize(item, PROTOCOL_VERSION) * WITNESS_SCALE_FACTOR;
    }
    return (weight + WITNESS_SCALE_FACTOR - 1) / WITNESS_SCALE_FACTOR;
}

std::string ConvertToPQCAddress(const std::string& address) {
    // Decode existing address
    CTxDestination dest = DecodeDestination(address);
    if (!IsValidDestination(dest)) {
        return "";
    }
    
    // Get public key hash
    uint160 pubKeyHash;
    if (auto* keyID = boost::get<PKHash>(&dest)) {
        pubKeyHash = uint160(*keyID);
    } else {
        return "";
    }
    
    // Create witness program
    std::vector<unsigned char> program;
    program.push_back(WITNESS_V2_PQC);  // Version 2
    
    // Add public key hash
    std::vector<unsigned char> hashBytes(pubKeyHash.begin(), pubKeyHash.end());
    program.insert(program.end(), hashBytes.begin(), hashBytes.end());
    
    // Convert to Bech32m
    std::string result;
    std::vector<unsigned char> data;
    ConvertBits<8, 5, true>([&](unsigned char c) { data.push_back(c); }, program.begin(), program.end());
    
    // Encode with bc1z prefix
    if (!bech32::Encode(result, "bc", 1, data)) {
        return "";
    }
    
    // Replace prefix with bc1z
    result.replace(0, 3, "bc1z");
    
    return result;
}

CScript CreatePQCWitnessProgram(const uint160& pubKeyHash) {
    CScript result;
    
    // Add witness version
    result << PQC_WITNESS_PROGRAM;
    
    // Add public key hash
    result << std::vector<unsigned char>(pubKeyHash.begin(), pubKeyHash.end());
    
    return result;
}

} // namespace pqc
