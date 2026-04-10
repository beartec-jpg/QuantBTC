// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <script/sigcache.h>

#include <crypto/sha256.h>
#include <logging.h>
#include <pubkey.h>
#include <random.h>
#include <script/interpreter.h>
#include <span.h>
#include <uint256.h>

#include <mutex>
#include <shared_mutex>
#include <vector>

SignatureCache::SignatureCache(const size_t max_size_bytes)
{
    uint256 nonce = GetRandHash();
    // We want the nonce to be 64 bytes long to force the hasher to process
    // this chunk, which makes later hash computations more efficient. We
    // just write our 32-byte entropy, and then pad with 'E' for ECDSA,
    // 'S' for Schnorr, and 'D' for Dilithium (followed by 0 bytes).
    static constexpr unsigned char PADDING_ECDSA[32] = {'E'};
    static constexpr unsigned char PADDING_SCHNORR[32] = {'S'};
    static constexpr unsigned char PADDING_DILITHIUM[32] = {'D'};
    m_salted_hasher_ecdsa.Write(nonce.begin(), 32);
    m_salted_hasher_ecdsa.Write(PADDING_ECDSA, 32);
    m_salted_hasher_schnorr.Write(nonce.begin(), 32);
    m_salted_hasher_schnorr.Write(PADDING_SCHNORR, 32);
    m_salted_hasher_dilithium.Write(nonce.begin(), 32);
    m_salted_hasher_dilithium.Write(PADDING_DILITHIUM, 32);

    const auto [num_elems, approx_size_bytes] = setValid.setup_bytes(max_size_bytes);
    LogPrintf("Using %zu MiB out of %zu MiB requested for signature cache, able to store %zu elements\n",
              approx_size_bytes >> 20, max_size_bytes >> 20, num_elems);
}

void SignatureCache::ComputeEntryECDSA(uint256& entry, const uint256& hash, const std::vector<unsigned char>& vchSig, const CPubKey& pubkey) const
{
    CSHA256 hasher = m_salted_hasher_ecdsa;
    hasher.Write(hash.begin(), 32).Write(pubkey.data(), pubkey.size()).Write(vchSig.data(), vchSig.size()).Finalize(entry.begin());
}

void SignatureCache::ComputeEntrySchnorr(uint256& entry, const uint256& hash, Span<const unsigned char> sig, const XOnlyPubKey& pubkey) const
{
    CSHA256 hasher = m_salted_hasher_schnorr;
    hasher.Write(hash.begin(), 32).Write(pubkey.data(), pubkey.size()).Write(sig.data(), sig.size()).Finalize(entry.begin());
}

void SignatureCache::ComputeEntryDilithium(uint256& entry, const uint256& hash, Span<const unsigned char> sig, Span<const unsigned char> pubkey) const
{
    CSHA256 hasher = m_salted_hasher_dilithium;
    hasher.Write(hash.begin(), 32).Write(pubkey.data(), pubkey.size()).Write(sig.data(), sig.size()).Finalize(entry.begin());
}

void SignatureCache::ComputeEntryDilithiumRaw(uint256& entry, Span<const unsigned char> pqc_sig, Span<const unsigned char> pqc_pubkey, Span<const unsigned char> ecdsa_sig, Span<const unsigned char> scriptCode, unsigned char sigversion) const
{
    CSHA256 hasher = m_salted_hasher_dilithium;
    hasher.Write(pqc_sig.data(), pqc_sig.size());
    hasher.Write(pqc_pubkey.data(), pqc_pubkey.size());
    hasher.Write(ecdsa_sig.data(), ecdsa_sig.size());
    hasher.Write(scriptCode.data(), scriptCode.size());
    hasher.Write(&sigversion, 1);
    hasher.Finalize(entry.begin());
}

void SignatureCache::ComputeEntryPQC(uint256& entry, Span<const unsigned char> pqc_sig, Span<const unsigned char> pqc_pubkey, Span<const unsigned char> scriptCode, unsigned char sigversion, unsigned char hashType) const
{
    CSHA256 hasher = m_salted_hasher_dilithium;
    hasher.Write(pqc_sig.data(), pqc_sig.size());
    hasher.Write(pqc_pubkey.data(), pqc_pubkey.size());
    hasher.Write(scriptCode.data(), scriptCode.size());
    hasher.Write(&sigversion, 1);
    hasher.Write(&hashType, 1);
    hasher.Finalize(entry.begin());
}

bool SignatureCache::Get(const uint256& entry, const bool erase)
{
    std::shared_lock<std::shared_mutex> lock(cs_sigcache);
    return setValid.contains(entry, erase);
}

void SignatureCache::Set(const uint256& entry)
{
    std::unique_lock<std::shared_mutex> lock(cs_sigcache);
    setValid.insert(entry);
}

bool CachingTransactionSignatureChecker::VerifyECDSASignature(const std::vector<unsigned char>& vchSig, const CPubKey& pubkey, const uint256& sighash) const
{
    uint256 entry;
    m_signature_cache.ComputeEntryECDSA(entry, sighash, vchSig, pubkey);
    if (m_signature_cache.Get(entry, !store)) {
        ++m_signature_cache.m_ecdsa_hits;
        return true;
    }
    ++m_signature_cache.m_ecdsa_misses;
    if (!TransactionSignatureChecker::VerifyECDSASignature(vchSig, pubkey, sighash))
        return false;
    if (store)
        m_signature_cache.Set(entry);
    return true;
}

bool CachingTransactionSignatureChecker::VerifySchnorrSignature(Span<const unsigned char> sig, const XOnlyPubKey& pubkey, const uint256& sighash) const
{
    uint256 entry;
    m_signature_cache.ComputeEntrySchnorr(entry, sighash, sig, pubkey);
    if (m_signature_cache.Get(entry, !store)) {
        ++m_signature_cache.m_schnorr_hits;
        return true;
    }
    ++m_signature_cache.m_schnorr_misses;
    if (!TransactionSignatureChecker::VerifySchnorrSignature(sig, pubkey, sighash)) return false;
    if (store) m_signature_cache.Set(entry);
    return true;
}

bool CachingTransactionSignatureChecker::CheckDilithiumSignature(const std::vector<unsigned char>& pqc_sig, const std::vector<unsigned char>& pqc_pubkey, const std::vector<unsigned char>& ecdsa_sig, const CScript& scriptCode, SigVersion sigversion) const
{
    uint256 entry;
    m_signature_cache.ComputeEntryDilithiumRaw(entry,
        Span<const unsigned char>(pqc_sig),
        Span<const unsigned char>(pqc_pubkey),
        Span<const unsigned char>(ecdsa_sig),
        Span<const unsigned char>(scriptCode.data(), scriptCode.size()),
        static_cast<unsigned char>(sigversion));
    if (m_signature_cache.Get(entry, !store)) {
        ++m_signature_cache.m_dilithium_hits;
        return true;
    }
    ++m_signature_cache.m_dilithium_misses;

    if (!TransactionSignatureChecker::CheckDilithiumSignature(pqc_sig, pqc_pubkey, ecdsa_sig, scriptCode, sigversion))
        return false;

    if (store) m_signature_cache.Set(entry);
    return true;
}

bool CachingTransactionSignatureChecker::CheckPQCSignature(const std::vector<unsigned char>& pqcSig, const std::vector<unsigned char>& pqcPubKey, const CScript& scriptCode, SigVersion sigversion, int nHashType) const
{
    uint256 entry;
    m_signature_cache.ComputeEntryPQC(entry,
        Span<const unsigned char>(pqcSig),
        Span<const unsigned char>(pqcPubKey),
        Span<const unsigned char>(scriptCode.data(), scriptCode.size()),
        static_cast<unsigned char>(sigversion),
        static_cast<unsigned char>(nHashType & 0xff));

    if (m_signature_cache.Get(entry, !store)) {
        ++m_signature_cache.m_dilithium_hits;
        return true;
    }
    ++m_signature_cache.m_dilithium_misses;

    if (!TransactionSignatureChecker::CheckPQCSignature(pqcSig, pqcPubKey, scriptCode, sigversion, nHashType))
        return false;

    if (store) m_signature_cache.Set(entry);
    return true;
}

bool CachingTransactionSignatureChecker::CheckSPHINCSSignature(const std::vector<unsigned char>& pqc_sig, const std::vector<unsigned char>& pqc_pubkey, const std::vector<unsigned char>& ecdsa_sig, const CScript& scriptCode, SigVersion sigversion) const
{
    // Build a cache entry using the Dilithium domain hasher (same PQC domain).
    uint256 entry;
    m_signature_cache.ComputeEntryDilithiumRaw(entry,
        Span<const unsigned char>(pqc_sig),
        Span<const unsigned char>(pqc_pubkey),
        Span<const unsigned char>(ecdsa_sig),
        Span<const unsigned char>(scriptCode.data(), scriptCode.size()),
        static_cast<unsigned char>(sigversion));

    if (m_signature_cache.Get(entry, !store)) {
        ++m_signature_cache.m_dilithium_hits;
        return true;
    }
    ++m_signature_cache.m_dilithium_misses;

    if (!TransactionSignatureChecker::CheckSPHINCSSignature(pqc_sig, pqc_pubkey, ecdsa_sig, scriptCode, sigversion))
        return false;

    if (store) m_signature_cache.Set(entry);
    return true;
}
