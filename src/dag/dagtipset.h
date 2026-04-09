// Copyright (c) 2026 BearTec / QuantumBTC
// Copyright (c) 2024 The QuantumBTC developers
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#ifndef BITCOIN_DAG_DAGTIPSET_H
#define BITCOIN_DAG_DAGTIPSET_H

/**
 * DagTipSet - tracks the current "tips" of the BlockDAG.
 *
 * A tip is a block that has no children yet. When mining a new block,
 * miners reference up to MAX_BLOCK_PARENTS tips as their parent hashes.
 *
 * Thread safety: all public methods must be called with cs_main held
 * (the same lock used by the chainstate).
 */

#include <uint256.h>

#include <map>
#include <set>
#include <vector>

namespace dag {

/** Maximum number of parent hashes a block header may contain.
 *  Must be >= the largest nMaxDagParents across all chain params (currently 64). */
static constexpr uint32_t MAX_BLOCK_PARENTS = 64;

/** Entries in m_known_scores older than this many blue_score units behind the
 *  best tip are pruned.  Reorgs deeper than this are practically impossible. */
static constexpr uint64_t KNOWN_SCORES_PRUNE_DEPTH = 1000;

/**
 * Maintains the set of current DAG tips, ordered by blue_score descending.
 *
 * Internally tips are stored in a set keyed by (blue_score DESC, hash ASC)
 * so that GetMiningParents() always returns the highest-scored tips first.
 * A separate hash→blue_score map enables O(log n) removal by hash.
 */
class DagTipSet {
public:
    DagTipSet() = default;

    /**
     * Add a newly verified block as a tip (also removes its parents from tips).
     * @param block_hash  hash of the accepted block
     * @param blue_score  GHOSTDAG blue_score of the accepted block
     * @param parents     all parent hashes (pprev + dagparents)
     */
    void BlockConnected(const uint256& block_hash, uint64_t blue_score,
                        const std::vector<uint256>& parents);

    /** Remove a block from tips when it is disconnected (reorg). */
    void BlockDisconnected(const uint256& block_hash,
                           const std::vector<uint256>& parent_hashes);

    /**
     * Return up to `max_parents` tip hashes for a new block template.
     * Returns tips in blue_score descending order (best tips first).
     */
    std::vector<uint256> GetMiningParents(uint32_t max_parents = MAX_BLOCK_PARENTS) const;

    /** Returns true if `hash` is currently a tip. */
    bool IsTip(const uint256& hash) const;

    /** Number of current tips. */
    size_t Size() const { return m_score_to_hash.size(); }

    /** Clear all state (used for unit tests / reindex). */
    void Clear();

private:
    /**
     * Comparator: higher blue_score first; ties broken by lower hash.
     * This gives a deterministic priority ordering for tip selection.
     */
    struct TipOrder {
        bool operator()(const std::pair<uint64_t, uint256>& a,
                        const std::pair<uint64_t, uint256>& b) const
        {
            if (a.first != b.first) return a.first > b.first; // higher score first
            return a.second < b.second;                        // lower hash first
        }
    };

    /** Ordered set of (blue_score, hash), best tip at begin(). */
    std::set<std::pair<uint64_t, uint256>, TipOrder> m_score_to_hash;

    /** Reverse lookup: hash → blue_score, for O(log n) removal. */
    std::map<uint256, uint64_t> m_hash_to_score;

    /** Historical lookup: hash → blue_score for known blocks (including non-tips). */
    std::map<uint256, uint64_t> m_known_scores;

    void RemoveTip(const uint256& hash);
    void InsertTip(const uint256& hash, uint64_t blue_score);

    /** Remove entries from m_known_scores that are far behind the best tip. */
    void PruneKnownScores(uint64_t best_score);
};

} // namespace dag

#endif // BITCOIN_DAG_DAGTIPSET_H
