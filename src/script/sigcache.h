// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_SCRIPT_SIGCACHE_H
#define BITCOIN_SCRIPT_SIGCACHE_H

#include <consensus/amount.h>
#include <crypto/sha256.h>
#include <cuckoocache.h>
#include <script/interpreter.h>
#include <span.h>
#include <uint256.h>
#include <util/hasher.h>

#include <atomic>
#include <cstddef>
#include <shared_mutex>
#include <vector>

class CPubKey;
class CTransaction;
class XOnlyPubKey;

// DoS prevention: limit cache size to 32MiB (over 1000000 entries on 64-bit
// systems). Due to how we count cache size, actual memory usage is slightly
// more (~32.25 MiB)
static constexpr size_t DEFAULT_VALIDATION_CACHE_BYTES{32 << 20};
static constexpr size_t DEFAULT_SIGNATURE_CACHE_BYTES{DEFAULT_VALIDATION_CACHE_BYTES / 2};
static constexpr size_t DEFAULT_SCRIPT_EXECUTION_CACHE_BYTES{DEFAULT_VALIDATION_CACHE_BYTES / 2};
static_assert(DEFAULT_VALIDATION_CACHE_BYTES == DEFAULT_SIGNATURE_CACHE_BYTES + DEFAULT_SCRIPT_EXECUTION_CACHE_BYTES);

/**
 * Valid signature cache, to avoid doing expensive ECDSA signature checking
 * twice for every transaction (once when accepted into memory pool, and
 * again when accepted into the block chain)
 */
class SignatureCache
{
private:
    //! Entries are SHA256(nonce || 'E' or 'S' or 'D' || 31 zero bytes || signature hash || public key || signature):
    CSHA256 m_salted_hasher_ecdsa;
    CSHA256 m_salted_hasher_schnorr;
    CSHA256 m_salted_hasher_dilithium;
    typedef CuckooCache::cache<uint256, SignatureCacheHasher> map_type;
    map_type setValid;
    std::shared_mutex cs_sigcache;

public:
    SignatureCache(size_t max_size_bytes);

    SignatureCache(const SignatureCache&) = delete;
    SignatureCache& operator=(const SignatureCache&) = delete;

    void ComputeEntryECDSA(uint256& entry, const uint256 &hash, const std::vector<unsigned char>& vchSig, const CPubKey& pubkey) const;
    void ComputeEntrySchnorr(uint256& entry, const uint256 &hash, Span<const unsigned char> sig, const XOnlyPubKey& pubkey) const;
    void ComputeEntryDilithium(uint256& entry, const uint256 &hash, Span<const unsigned char> sig, Span<const unsigned char> pubkey) const;
    void ComputeEntryDilithiumRaw(uint256& entry, Span<const unsigned char> pqc_sig, Span<const unsigned char> pqc_pubkey, Span<const unsigned char> ecdsa_sig, Span<const unsigned char> scriptCode, unsigned char sigversion) const;
    void ComputeEntryPQC(uint256& entry, Span<const unsigned char> pqc_sig, Span<const unsigned char> pqc_pubkey, Span<const unsigned char> scriptCode, unsigned char sigversion, unsigned char hashType) const;

    bool Get(const uint256& entry, const bool erase);

    void Set(const uint256& entry);

    // ── Per-algorithm cache hit / miss counters (lock-free) ──────────
    mutable std::atomic<uint64_t> m_ecdsa_hits{0};
    mutable std::atomic<uint64_t> m_ecdsa_misses{0};
    mutable std::atomic<uint64_t> m_schnorr_hits{0};
    mutable std::atomic<uint64_t> m_schnorr_misses{0};
    mutable std::atomic<uint64_t> m_dilithium_hits{0};
    mutable std::atomic<uint64_t> m_dilithium_misses{0};
};

class CachingTransactionSignatureChecker : public TransactionSignatureChecker
{
private:
    bool store;
    SignatureCache& m_signature_cache;

public:
    CachingTransactionSignatureChecker(const CTransaction* txToIn, unsigned int nInIn, const CAmount& amountIn, bool storeIn, SignatureCache& signature_cache, PrecomputedTransactionData& txdataIn) : TransactionSignatureChecker(txToIn, nInIn, amountIn, txdataIn, MissingDataBehavior::ASSERT_FAIL), store(storeIn), m_signature_cache(signature_cache)  {}

    bool VerifyECDSASignature(const std::vector<unsigned char>& vchSig, const CPubKey& vchPubKey, const uint256& sighash) const override;
    bool VerifySchnorrSignature(Span<const unsigned char> sig, const XOnlyPubKey& pubkey, const uint256& sighash) const override;
    bool CheckDilithiumSignature(const std::vector<unsigned char>& pqc_sig, const std::vector<unsigned char>& pqc_pubkey, const std::vector<unsigned char>& ecdsa_sig, const CScript& scriptCode, SigVersion sigversion) const override;
    bool CheckPQCSignature(const std::vector<unsigned char>& pqcSig, const std::vector<unsigned char>& pqcPubKey, const CScript& scriptCode, SigVersion sigversion, int nHashType) const override;
    bool CheckSPHINCSSignature(const std::vector<unsigned char>& pqc_sig, const std::vector<unsigned char>& pqc_pubkey, const std::vector<unsigned char>& ecdsa_sig, const CScript& scriptCode, SigVersion sigversion) const override;
};

#endif // BITCOIN_SCRIPT_SIGCACHE_H
