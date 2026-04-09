// Copyright (c) 2026 BearTec / QuantumBTC
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#include <consensus/pqc_witness.h>
#include <hash.h>
#include <addresstype.h>
#include <bech32.h>
#include <key_io.h>
#include <serialize.h>
#include <util/strencodings.h>

namespace pqc {

size_t PQCWitness::GetVirtualSize() const {
    size_t weight = 0;
    // Calculate weight similar to SegWit
    for (const auto& item : stack) {
        weight += GetSerializeSize(item) * WITNESS_SCALE_FACTOR;
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
    if (const auto* keyID = std::get_if<PKHash>(&dest)) {
        pubKeyHash = uint160(*keyID);
    } else {
        return "";
    }

    // Create witness program: version byte + pubkey hash
    std::vector<unsigned char> program;
    program.push_back(WITNESS_V2_PQC);  // Version 2
    std::vector<unsigned char> hashBytes(pubKeyHash.begin(), pubKeyHash.end());
    program.insert(program.end(), hashBytes.begin(), hashBytes.end());

    // Convert to 5-bit groups for bech32 encoding
    std::vector<uint8_t> data;
    ConvertBits<8, 5, true>([&](unsigned char c) { data.push_back(c); },
                            program.begin(), program.end());

    // Encode as Bech32m with "bc" HRP
    return bech32::Encode(bech32::Encoding::BECH32M, "bc", data);
}

CScript CreatePQCWitnessProgram(const uint160& pubKeyHash) {
    CScript result;
    result << PQC_WITNESS_PROGRAM;
    result << std::vector<unsigned char>(pubKeyHash.begin(), pubKeyHash.end());
    return result;
}

} // namespace pqc
