#ifndef BITCOIN_CONSENSUS_PQC_WITNESS_H
#define BITCOIN_CONSENSUS_PQC_WITNESS_H

#include <primitives/transaction.h>
#include <script/script.h>
#include <version.h>

/** Witness version for PQC transactions */
static const int WITNESS_V2_PQC = 2;

/** PQC witness program version */
static const std::vector<unsigned char> PQC_WITNESS_PROGRAM = {0x02}; // Version 2

namespace pqc {

/**
 * PQC witness structure
 * Follows SegWit principles for storing PQC signatures
 */
class PQCWitness {
public:
    std::vector<std::vector<unsigned char>> stack;
    
    PQCWitness() {}
    
    explicit PQCWitness(const std::vector<std::vector<unsigned char>>& witnessStack)
        : stack(witnessStack) {}
    
    bool IsNull() const { return stack.empty(); }
    
    /**
     * Get the witness version
     * @return witness version (2 for PQC)
     */
    int GetVersion() const { return WITNESS_V2_PQC; }
    
    /**
     * Calculate witness size
     * @return size in virtual bytes
     */
    size_t GetVirtualSize() const;
};

/**
 * Convert a classical address to PQC-enabled address
 * @param[in] address The classical address to convert
 * @return Bech32m address with witness version 2 (bc1z prefix)
 */
std::string ConvertToPQCAddress(const std::string& address);

/**
 * Create PQC witness program
 * @param[in] pubKeyHash Hash of the public key
 * @return Witness program for PQC
 */
CScript CreatePQCWitnessProgram(const uint160& pubKeyHash);

} // namespace pqc

#endif // BITCOIN_CONSENSUS_PQC_WITNESS_H
