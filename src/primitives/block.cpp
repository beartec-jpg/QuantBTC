// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2019 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <primitives/block.h>

#include <hash.h>
#include <tinyformat.h>

uint256 CBlockHeader::ComputeParentsRoot(const std::vector<uint256>& parents)
{
    if (parents.empty()) return uint256{};
    // Double-SHA256 of the concatenated parent hashes, consistent with
    // Bitcoin's hash-of-data convention (e.g. merkle root computation).
    HashWriter h{};
    for (const uint256& p : parents) {
        h << p;
    }
    return h.GetHash();
}

uint256 CBlockHeader::GetHash() const
{
    // For non-DAG blocks: hash the standard 80-byte header.
    // For DAG blocks: include hashParentsRoot (placed between nBits and nNonce)
    // so that miners commit to the entire DAG parent set.  This prevents an
    // adversary from stripping or replacing hashParents after a block is mined.
    HashWriter hasher{};
    hasher << nVersion << hashPrevBlock << hashMerkleRoot << nTime << nBits;
    if (IsDagBlock()) {
        hasher << hashParentsRoot;
    }
    hasher << nNonce;
    return hasher.GetHash();
}

std::string CBlock::ToString() const
{
    std::stringstream s;
    s << strprintf("CBlock(hash=%s, ver=0x%08x, hashPrevBlock=%s, hashMerkleRoot=%s, nTime=%u, nBits=%08x, nNonce=%u, vtx=%u)\n",
        GetHash().ToString(),
        nVersion,
        hashPrevBlock.ToString(),
        hashMerkleRoot.ToString(),
        nTime, nBits, nNonce,
        vtx.size());
    for (const auto& tx : vtx) {
        s << "  " << tx->ToString() << "\n";
    }
    return s.str();
}
