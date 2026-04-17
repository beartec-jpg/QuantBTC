#ifndef BITCOIN_SCRIPT_PQCSCRIPT_H
#define BITCOIN_SCRIPT_PQCSCRIPT_H

#include <attributes.h>
#include <pubkey.h>
#include <script/script.h>
#include <uint256.h>
#include <util/hash_type.h>

#include <variant>
#include <vector>

// Post-quantum cryptography specific script types and functions

// PQC-specific script verification flags
static const unsigned int SCRIPT_VERIFY_PQC = (1U << 31); // Enable PQC verification

// PQC-specific output types
enum class PQCTxoutType {
    NONSTANDARD,
    PQC_PUBKEY,          // PQC public key only
    PQC_PUBKEYHASH,      // PQC public key hash
    PQC_SCRIPTHASH,      // PQC script hash
    PQC_MULTISIG,        // Multiple PQC signature
    PQC_NULL_DATA,       // Data-carrying output with PQC protection
    PQC_WITNESS_V0       // PQC witness version 0 script
};

// PQC-specific destination types
struct PQCPubKeyHash : public BaseHash<uint256> {  // Using uint256 for potentially larger PQC hashes
    PQCPubKeyHash() : BaseHash() {}
    explicit PQCPubKeyHash(const uint256& hash) : BaseHash(hash) {}
    // Add constructors for specific PQC public key types later
};

struct PQCScriptHash : public BaseHash<uint256> {
    PQCScriptHash() : BaseHash() {}
    explicit PQCScriptHash(const uint256& hash) : BaseHash(hash) {}
    explicit PQCScriptHash(const CScript& script);  // Implementation in cpp file
};

// Get human-readable string for PQC output type
std::string GetPQCTxnOutputType(PQCTxoutType t);

// Create script for PQC destination
CScript GetScriptForPQCDestination(const PQCPubKeyHash& dest);

// Create script for raw PQC public key
CScript GetScriptForPQCPubKey(const std::vector<unsigned char>& pubkey);

// Create script for multiple PQC signatures
CScript GetScriptForPQCMultisig(int nRequired, const std::vector<std::vector<unsigned char>>& keys);

// Extract PQC destination from script
bool ExtractPQCDestination(const CScript& scriptPubKey, PQCPubKeyHash& addressRet);

// Solve PQC script templates
PQCTxoutType SolvePQC(const CScript& scriptPubKey, std::vector<std::vector<unsigned char>>& vSolutionsRet);

#endif // BITCOIN_SCRIPT_PQCSCRIPT_H
