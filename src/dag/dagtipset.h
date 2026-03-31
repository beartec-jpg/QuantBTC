// Copyright (c) 2026 beartec-jpg / QuantumBTC
// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

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

#include <set>
#include <vector>

namespace dag {

/** Maximum number of parent hashes a block header may contain. */
static constexpr uint32_t MAX_BLOCK_PARENTS = 32;

/**
 * Maintains the set of current DAG tips.
 *
 * Tips are ordered by (blue_score DESC, hash ASC) so the "best" tip is
 * always tips.begin().
 */
class DagTipSet {
public:
    DagTipSet() = default;

    /** Add a newly verified block as a tip (also removes its parents from tips). */
    void BlockConnected(const uint256& block_hash, const std::vector<uint256>& parents);

    /** Remove a block from tips when it is disconnected (reorg). */
    void BlockDisconnected(const uint256& block_hash, const std::vector<uint256>& parents);

    /**
     * Return up to `max_parents` tip hashes for a new block template.
     * Selects the most-work tips first.
     */
    std::vector<uint256> GetMiningParents(uint32_t max_parents = MAX_BLOCK_PARENTS) const;

    /** Returns true if `hash` is currently a tip. */
    bool IsTip(const uint256& hash) const;

    /** Number of current tips. */
    size_t Size() const { return m_tips.size(); }

    /** Access all tips (unordered). */
    const std::set<uint256>& GetTips() const { return m_tips; }

    /** Clear all state (used for unit tests / reindex). */
    void Clear();

private:
    std::set<uint256> m_tips;
};

} // namespace dag

#endif // BITCOIN_DAG_DAGTIPSET_H
