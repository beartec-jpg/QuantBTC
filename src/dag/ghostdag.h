// Copyright (c) 2026 beartec-jpg / QuantumBTC
// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_DAG_GHOSTDAG_H
#define BITCOIN_DAG_GHOSTDAG_H

/**
 * GHOSTDAG consensus for QuantumBTC BlockDAG.
 *
 * Implementation of the GHOSTDAG/PHANTOM protocol as described in:
 *   "PHANTOM: A Scalable BlockDAG Protocol" (Sompolinsky & Zohar, 2018)
 *   "GHOSTDAG: Greedy Heaviest-Observed Sub-Tree DAG" (Kaspa variant)
 *
 * Key concepts:
 *  - A block may reference multiple parent blocks (tips of the DAG).
 *  - GHOSTDAG assigns every block a "blue score" and classifies it as
 *    blue (in the "selected" chain / honest sub-DAG) or red (off-chain).
 *  - The "virtual" block is the imaginary block that selects all current
 *    tips as parents, used for ordering and UTXO state.
 *  - The parameter K controls how many blocks per round are expected to
 *    be mined concurrently; larger K tolerates more parallelism.
 *
 * Simplified implementation notes for QuantumBTC:
 *  - We use iterative DFS-based blue set computation.
 *  - Anti-cone size is capped at K to determine blue/red classification.
 *  - Topological ordering follows blue score then hash for determinism.
 */

#include <cstdint>
#include <set>
#include <unordered_map>
#include <unordered_set>
#include <util/hasher.h>
#include <vector>

#include <uint256.h>

namespace dag {

/** Maximum anti-cone size for a blue block (GHOSTDAG K parameter). */
static constexpr uint32_t DEFAULT_GHOSTDAG_K = 18;

/**
 * Per-block GHOSTDAG data stored alongside CBlockIndex.
 * This is memory-only; reconstructed on load from the DAG topology.
 */
struct GhostdagData {
    /** Blue score: number of blue blocks in this block's past (inclusive). */
    uint64_t blue_score{0};

    /** The selected parent block hash (the blue parent with highest blue score). */
    uint256 selected_parent{};

    /** Ordered list of blue blocks in this block's mergeset (relative to selected parent). */
    std::vector<uint256> mergeset_blues{};

    /** Red blocks in this block's mergeset (ordered by topological sort). */
    std::vector<uint256> mergeset_reds{};

    /** Blue work (accumulated PoW work of blue blocks). */
    uint64_t blue_work{0};

    bool IsNull() const { return selected_parent.IsNull(); }
};

/**
 * Interface for querying DAG block info during GHOSTDAG computation.
 * Concrete implementation provided by the chainstate / block index.
 */
class IGhostdagBlockProvider {
public:
    virtual ~IGhostdagBlockProvider() = default;

    /** Returns the GHOSTDAG data for block `hash`, or nullptr if unknown. */
    virtual const GhostdagData* GetGhostdagData(const uint256& hash) const = 0;

    /** Returns the parent hashes of block `hash`. */
    virtual std::vector<uint256> GetParents(const uint256& hash) const = 0;

    /** Returns true if `ancestor` is in the past of `block` (i.e. reachable). */
    virtual bool IsAncestorOf(const uint256& ancestor, const uint256& block) const = 0;

    /** Returns the PoW work (compact representation) for block `hash`. */
    virtual uint64_t GetBlockWork(const uint256& hash) const = 0;
};

/**
 * GHOSTDAG algorithm.
 *
 * Given a DAG block (identified by its parent hashes), computes the
 * GhostdagData for that block: selected parent, blue/red mergeset, blue score.
 */
class GhostdagManager {
public:
    explicit GhostdagManager(uint32_t k = DEFAULT_GHOSTDAG_K) : m_k(k) {}

    /**
     * Compute GHOSTDAG data for a new block given its parent hashes.
     *
     * @param parents     - set of parent block hashes for the new block
     * @param provider    - callback interface to query existing DAG data
     * @return            - computed GhostdagData for the new block
     */
    GhostdagData ComputeGhostdag(
        const std::vector<uint256>& parents,
        const IGhostdagBlockProvider& provider) const;

    /**
     * Select the best parent (highest blue score, tie-break by hash).
     */
    uint256 SelectBestParent(
        const std::vector<uint256>& candidates,
        const IGhostdagBlockProvider& provider) const;

    /**
     * Compute the "virtual" block GHOSTDAG data (all current tips as parents).
     */
    GhostdagData ComputeVirtual(
        const std::vector<uint256>& tips,
        const IGhostdagBlockProvider& provider) const;

    /**
     * Produce a topological ordering of blocks from genesis to virtual,
     * respecting blue score ordering (blue blocks ordered by blue score,
     * red blocks interleaved in a canonical position).
     *
     * @param all_blocks    - complete set of block hashes in the DAG
     * @param virtual_data  - GHOSTDAG data of the virtual block
     * @param provider      - DAG provider interface
     * @return              - ordered vector of block hashes (genesis first)
     */
    std::vector<uint256> TopologicalOrder(
        const std::unordered_set<uint256, BlockHasher>& all_blocks,
        const GhostdagData& virtual_data,
        const IGhostdagBlockProvider& provider) const;

    uint32_t GetK() const { return m_k; }

private:
    uint32_t m_k;

    /**
     * Walk the "selected parent chain" from block back to genesis,
     * collecting hashes.
     */
    std::vector<uint256> SelectedParentChain(
        const uint256& block,
        const IGhostdagBlockProvider& provider) const;

    /**
     * Compute the mergeset of a block relative to its selected parent:
     * all blocks in the block's past that are NOT in the selected parent's past
     * (excluding the selected parent itself).
     *
     * @param block_parents  - parent hashes of the block being processed
     * @param selected_parent - the chosen selected parent
     * @param provider        - DAG provider interface
     * @return                - ordered mergeset (topological order within)
     */
    std::vector<uint256> ComputeMergeset(
        const std::vector<uint256>& block_parents,
        const uint256& selected_parent,
        const IGhostdagBlockProvider& provider) const;

    /**
     * From a mergeset, classify each block as blue or red using the
     * anti-cone size check (anti-cone relative to blues ≤ K → blue).
     */
    void ClassifyMergeset(
        const std::vector<uint256>& mergeset,
        const std::vector<uint256>& inherited_blues, // blues from selected parent chain
        std::vector<uint256>& out_blues,
        std::vector<uint256>& out_reds,
        const IGhostdagBlockProvider& provider) const;

    /**
     * Count how many blocks in `blue_candidates` are in the anti-cone of
     * `block` (i.e. neither ancestors nor descendants of `block`).
     */
    uint32_t AntiConeBlueCount(
        const uint256& block,
        const std::vector<uint256>& blue_candidates,
        const IGhostdagBlockProvider& provider) const;
};

/**
 * Virtual chain: the sequence of selected parents from virtual block back
 * to genesis. This is the "main chain" equivalent in a BlockDAG.
 */
std::vector<uint256> ComputeVirtualSelectedParentChain(
    const std::vector<uint256>& tips,
    const IGhostdagBlockProvider& provider,
    uint32_t k = DEFAULT_GHOSTDAG_K);

} // namespace dag

#endif // BITCOIN_DAG_GHOSTDAG_H
