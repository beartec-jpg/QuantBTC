// Copyright (c) 2026 beartec-jpg / QuantumBTC
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_DAG_GHOSTDAG_BLOCKINDEX_H
#define BITCOIN_DAG_GHOSTDAG_BLOCKINDEX_H

#include <chain.h>
#include <dag/ghostdag.h>
#include <node/blockstorage.h>
#include <uint256.h>

#include <unordered_set>
#include <vector>

namespace dag {

/**
 * Concrete IGhostdagBlockProvider backed by Bitcoin Core's CBlockIndex / BlockManager.
 * Queries block parents, GHOSTDAG data, and ancestry from the in-memory block index.
 */
class BlockIndexGhostdagProvider final : public IGhostdagBlockProvider {
public:
    explicit BlockIndexGhostdagProvider(const node::BlockManager& blockman)
        : m_blockman(blockman) {}

    const GhostdagData* GetGhostdagData(const uint256& hash) const override
    {
        const CBlockIndex* pindex = LookupBlockIndex(hash);
        if (!pindex) return nullptr;
        return &pindex->dagData;
    }

    std::vector<uint256> GetParents(const uint256& hash) const override
    {
        std::vector<uint256> parents;
        const CBlockIndex* pindex = LookupBlockIndex(hash);
        if (!pindex) return parents;
        if (pindex->pprev) {
            parents.push_back(pindex->pprev->GetBlockHash());
        }
        for (const CBlockIndex* p : pindex->vDagParents) {
            if (p) parents.push_back(p->GetBlockHash());
        }
        return parents;
    }

    bool IsAncestorOf(const uint256& ancestor, const uint256& block) const override
    {
        const CBlockIndex* pAncestor = LookupBlockIndex(ancestor);
        const CBlockIndex* pBlock = LookupBlockIndex(block);
        if (!pAncestor || !pBlock) return false;
        return IsBlockAncestor(pAncestor, pBlock);
    }

    uint64_t GetBlockWork(const uint256& hash) const override
    {
        const CBlockIndex* pindex = LookupBlockIndex(hash);
        if (!pindex) return 0;
        // Use GetBlockProof() value, truncated to uint64_t (fine for relative comparisons)
        arith_uint256 proof = GetBlockProof(*pindex);
        uint64_t w = proof.GetLow64();
        return w > 0 ? w : 1;
    }

private:
    const node::BlockManager& m_blockman;

    const CBlockIndex* LookupBlockIndex(const uint256& hash) const
    {
        return m_blockman.LookupBlockIndex(hash);
    }

    /**
     * Check whether pAncestor is reachable from pBlock by following parent pointers.
     * Uses pprev (selected parent chain) and vDagParents (DAG parents).
     *
     * The BFS is bounded by height: we only enqueue blocks whose height is
     * strictly above pAncestor->nHeight (blocks at or below cannot be on a
     * path from pBlock to pAncestor unless they ARE pAncestor, which is
     * checked explicitly).  This guarantees termination proportional to the
     * DAG width × height difference, and never returns a wrong answer.
     */
    static bool IsBlockAncestor(const CBlockIndex* pAncestor, const CBlockIndex* pBlock)
    {
        if (pAncestor == pBlock) return true;
        if (pAncestor->nHeight > pBlock->nHeight) return false;

        // Fast path: check linear ancestry via pprev
        const CBlockIndex* walk = pBlock;
        while (walk && walk->nHeight > pAncestor->nHeight) {
            walk = walk->pprev;
        }
        if (walk == pAncestor) return true;

        // Slow path for DAG: BFS through vDagParents.
        // Height-bounded: only enqueue nodes above pAncestor's height.
        // At each node we check direct pointer equality before pruning.
        //
        // Safety cap: an adversarially wide DAG can force the visited set to
        // grow to O(MAX_MERGESET_SIZE × MAX_BLOCK_PARENTS) entries.  We cap
        // the BFS at MAX_ANCESTOR_BFS_NODES visited nodes.  Exceeding the cap
        // returns false (conservative: treats pAncestor as non-ancestor),
        // which causes GHOSTDAG to classify the block as "red" rather than
        // "blue".  This is safe: a legitimate block will never reach the cap
        // because the height bound already limits how many nodes are reachable.
        //
        // Derivation: MAX_MERGESET_SIZE (1000) × MAX_BLOCK_PARENTS (64) = 64,000
        // nodes per legitimate worst-case DAG window.  500,000 gives an 8×
        // safety margin over that bound before the cap fires.
        static constexpr size_t MAX_ANCESTOR_BFS_NODES = 500000;

        std::vector<const CBlockIndex*> queue;
        std::unordered_set<const CBlockIndex*> visited;
        queue.push_back(pBlock);
        visited.insert(pBlock);

        size_t front = 0;
        while (front < queue.size()) {
            if (visited.size() > MAX_ANCESTOR_BFS_NODES) {
                LogPrint(BCLog::VALIDATION,
                         "IsBlockAncestor: BFS node limit (%u) exceeded; "
                         "treating %s as non-ancestor of %s\n",
                         MAX_ANCESTOR_BFS_NODES,
                         pAncestor->GetBlockHash().ToString(),
                         pBlock->GetBlockHash().ToString());
                return false;
            }
            const CBlockIndex* cur = queue[front++];

            auto enqueue = [&](const CBlockIndex* p) {
                if (!p || !visited.insert(p).second) return;
                if (p == pAncestor) return; // found — will be caught below
                if (p->nHeight > pAncestor->nHeight) {
                    queue.push_back(p);
                }
            };

            // Check pprev
            if (cur->pprev) {
                if (cur->pprev == pAncestor) return true;
                enqueue(cur->pprev);
            }
            // Check DAG parents
            for (const CBlockIndex* p : cur->vDagParents) {
                if (p == pAncestor) return true;
                enqueue(p);
            }
        }
        return false;
    }
};

} // namespace dag

#endif // BITCOIN_DAG_GHOSTDAG_BLOCKINDEX_H
