// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2022 The Bitcoin Core developers
// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_PRIMITIVES_BLOCK_H
#define BITCOIN_PRIMITIVES_BLOCK_H

#include <primitives/transaction.h>
#include <serialize.h>
#include <uint256.h>
#include <util/time.h>

#include <vector>

/**
 * nVersion bit flag indicating this block uses QuantumBTC BlockDAG mode.
 * When set, the block serialization includes a hashParents vector after
 * the standard 80-byte header fields, encoding additional parent hashes
 * beyond hashPrevBlock (which holds the "selected parent" / best parent).
 */
static constexpr int32_t BLOCK_VERSION_DAGMODE = (1 << 28);

/** Nodes collect new transactions into a block, hash them into a hash tree,
 * and scan through nonce values to make the block's hash satisfy proof-of-work
 * requirements.  When they solve the proof-of-work, they broadcast the block
 * to everyone and the block is added to the block chain.  The first transaction
 * in the block is a special one that creates a new coin owned by the creator
 * of the block.
 */
class CBlockHeader
{
public:
    // header (standard 80-byte PoW-covered fields)
    int32_t nVersion;
    uint256 hashPrevBlock;   //!< Selected parent (highest blue score parent)
    uint256 hashMerkleRoot;
    uint32_t nTime;
    uint32_t nBits;
    uint32_t nNonce;

    /**
     * BlockDAG: additional parent hashes beyond the selected parent.
     * Only present when (nVersion & BLOCK_VERSION_DAGMODE) != 0.
     * hashPrevBlock always holds the "selected parent" (best scoring tip).
     * hashParents holds the remaining referenced tips (up to MAX_BLOCK_PARENTS-1).
     * All parent hashes together define the block's position in the DAG.
     *
     * NOTE: hashParents is serialized AFTER the standard PoW header, so
     * SHA-256 mining hardware covers the 80-byte base header as usual.
     * GetHash() hashes ONLY the 80-byte base header (for PoW & block id).
     * hashParents are committed via network serialization & DAG validation.
     */
    std::vector<uint256> hashParents;

    CBlockHeader()
    {
        SetNull();
    }

    /**
     * Serialization: standard 80-byte fields first, then optional DAG parents.
     * The PoW hash (GetHash()) covers only the first 80 bytes.
     * hashParents are included in serialization for P2P relay and
     * persistent storage, but not in the block-identity hash.
     */
    SERIALIZE_METHODS(CBlockHeader, obj)
    {
        READWRITE(obj.nVersion, obj.hashPrevBlock, obj.hashMerkleRoot,
                  obj.nTime, obj.nBits, obj.nNonce);
        if (obj.nVersion & BLOCK_VERSION_DAGMODE) {
            READWRITE(obj.hashParents);
        }
    }

    void SetNull()
    {
        nVersion = 0;
        hashPrevBlock.SetNull();
        hashMerkleRoot.SetNull();
        nTime = 0;
        nBits = 0;
        nNonce = 0;
        hashParents.clear();
    }

    bool IsNull() const
    {
        return (nBits == 0);
    }

    /** Returns true if this block is operating in BlockDAG mode. */
    bool IsDagBlock() const { return (nVersion & BLOCK_VERSION_DAGMODE) != 0; }

    /**
     * Returns all parent hashes: selected parent (hashPrevBlock) first,
     * then any additional parents from hashParents.
     */
    std::vector<uint256> GetAllParents() const
    {
        std::vector<uint256> all;
        if (!hashPrevBlock.IsNull()) {
            all.push_back(hashPrevBlock);
        }
        for (const uint256& p : hashParents) {
            if (!p.IsNull()) all.push_back(p);
        }
        return all;
    }

    uint256 GetHash() const;

    NodeSeconds Time() const
    {
        return NodeSeconds{std::chrono::seconds{nTime}};
    }

    int64_t GetBlockTime() const
    {
        return (int64_t)nTime;
    }
};


class CBlock : public CBlockHeader
{
public:
    // network and disk
    std::vector<CTransactionRef> vtx;

    // Memory-only flags for caching expensive checks
    mutable bool fChecked;                            // CheckBlock()
    mutable bool m_checked_witness_commitment{false}; // CheckWitnessCommitment()
    mutable bool m_checked_merkle_root{false};        // CheckMerkleRoot()

    CBlock()
    {
        SetNull();
    }

    CBlock(const CBlockHeader &header)
    {
        SetNull();
        *(static_cast<CBlockHeader*>(this)) = header;
    }

    SERIALIZE_METHODS(CBlock, obj)
    {
        READWRITE(AsBase<CBlockHeader>(obj), obj.vtx);
    }

    void SetNull()
    {
        CBlockHeader::SetNull();
        vtx.clear();
        fChecked = false;
        m_checked_witness_commitment = false;
        m_checked_merkle_root = false;
    }

    CBlockHeader GetBlockHeader() const
    {
        CBlockHeader block;
        block.nVersion       = nVersion;
        block.hashPrevBlock  = hashPrevBlock;
        block.hashMerkleRoot = hashMerkleRoot;
        block.nTime          = nTime;
        block.nBits          = nBits;
        block.nNonce         = nNonce;
        block.hashParents    = hashParents;
        return block;
    }

    std::string ToString() const;
};

/** Describes a place in the block chain to another node such that if the
 * other node doesn't have the same branch, it can find a recent common trunk.
 * The further back it is, the further before the fork it may be.
 */
struct CBlockLocator
{
    /** Historically CBlockLocator's version field has been written to network
     * streams as the negotiated protocol version and to disk streams as the
     * client version, but the value has never been used.
     *
     * Hard-code to the highest protocol version ever written to a network stream.
     * SerParams can be used if the field requires any meaning in the future,
     **/
    static constexpr int DUMMY_VERSION = 70016;

    std::vector<uint256> vHave;

    CBlockLocator() = default;

    explicit CBlockLocator(std::vector<uint256>&& have) : vHave(std::move(have)) {}

    SERIALIZE_METHODS(CBlockLocator, obj)
    {
        int nVersion = DUMMY_VERSION;
        READWRITE(nVersion);
        READWRITE(obj.vHave);
    }

    void SetNull()
    {
        vHave.clear();
    }

    bool IsNull() const
    {
        return vHave.empty();
    }
};

#endif // BITCOIN_PRIMITIVES_BLOCK_H
