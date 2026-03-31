// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <dag/ghostdag.h>

#include <algorithm>
#include <cassert>
#include <queue>

namespace dag {

// ---------------------------------------------------------------------------
// GhostdagManager::SelectBestParent
// ---------------------------------------------------------------------------
uint256 GhostdagManager::SelectBestParent(
    const std::vector<uint256>& candidates,
    const IGhostdagBlockProvider& provider) const
{
    if (candidates.empty()) return uint256{};

    uint256 best = candidates[0];
    const GhostdagData* best_data = provider.GetGhostdagData(best);
    uint64_t best_score = best_data ? best_data->blue_score : 0;

    for (size_t i = 1; i < candidates.size(); ++i) {
        const GhostdagData* d = provider.GetGhostdagData(candidates[i]);
        uint64_t score = d ? d->blue_score : 0;
        if (score > best_score ||
            (score == best_score && candidates[i] < best)) {
            best = candidates[i];
            best_score = score;
        }
    }
    return best;
}

// ---------------------------------------------------------------------------
// GhostdagManager::SelectedParentChain
// ---------------------------------------------------------------------------
std::vector<uint256> GhostdagManager::SelectedParentChain(
    const uint256& block,
    const IGhostdagBlockProvider& provider) const
{
    std::vector<uint256> chain;
    uint256 cur = block;
    while (!cur.IsNull()) {
        chain.push_back(cur);
        const GhostdagData* d = provider.GetGhostdagData(cur);
        if (!d || d->selected_parent.IsNull()) break;
        cur = d->selected_parent;
    }
    return chain; // tip → genesis order
}

// ---------------------------------------------------------------------------
// GhostdagManager::ComputeMergeset
//
// The mergeset of block B relative to its selected parent P is the set of
// blocks that are in past(B) but NOT in past(P) ∪ {P}.
// We compute this by starting from B's non-selected parents and doing a
// BFS/DFS backward, stopping when we reach blocks that are ancestors of P.
// ---------------------------------------------------------------------------
std::vector<uint256> GhostdagManager::ComputeMergeset(
    const std::vector<uint256>& block_parents,
    const uint256& selected_parent,
    const IGhostdagBlockProvider& provider) const
{
    std::vector<uint256> mergeset;
    std::unordered_set<uint256> visited;
    visited.insert(selected_parent);

    // BFS queue: start from all parents except the selected parent
    std::queue<uint256> q;
    for (const uint256& p : block_parents) {
        if (p != selected_parent && visited.find(p) == visited.end()) {
            visited.insert(p);
            mergeset.push_back(p);
            q.push(p);
        }
    }

    while (!q.empty()) {
        uint256 cur = q.front();
        q.pop();

        if (provider.IsAncestorOf(cur, selected_parent)) {
            // cur is an ancestor of selected_parent, don't go further
            continue;
        }

        std::vector<uint256> pars = provider.GetParents(cur);
        for (const uint256& p : pars) {
            if (visited.find(p) == visited.end() && !p.IsNull()) {
                visited.insert(p);
                // Only add to mergeset if not an ancestor of selected_parent
                if (!provider.IsAncestorOf(p, selected_parent)) {
                    mergeset.push_back(p);
                }
                q.push(p);
            }
        }
    }

    // Sort mergeset in topological order (by blue score ascending, then hash)
    std::sort(mergeset.begin(), mergeset.end(),
        [&](const uint256& a, const uint256& b) {
            const GhostdagData* da = provider.GetGhostdagData(a);
            const GhostdagData* db = provider.GetGhostdagData(b);
            uint64_t sa = da ? da->blue_score : 0;
            uint64_t sb = db ? db->blue_score : 0;
            if (sa != sb) return sa < sb;
            return a < b;
        });

    return mergeset;
}

// ---------------------------------------------------------------------------
// GhostdagManager::AntiConeBlueCount
// ---------------------------------------------------------------------------
uint32_t GhostdagManager::AntiConeBlueCount(
    const uint256& block,
    const std::vector<uint256>& blue_candidates,
    const IGhostdagBlockProvider& provider) const
{
    uint32_t count = 0;
    for (const uint256& blue : blue_candidates) {
        if (blue == block) continue;
        // In anti-cone: neither ancestor nor descendant
        bool is_ancestor = provider.IsAncestorOf(blue, block);
        bool is_descendant = provider.IsAncestorOf(block, blue);
        if (!is_ancestor && !is_descendant) {
            ++count;
        }
    }
    return count;
}

// ---------------------------------------------------------------------------
// GhostdagManager::ClassifyMergeset
// ---------------------------------------------------------------------------
void GhostdagManager::ClassifyMergeset(
    const std::vector<uint256>& mergeset,
    const std::vector<uint256>& inherited_blues,
    std::vector<uint256>& out_blues,
    std::vector<uint256>& out_reds,
    const IGhostdagBlockProvider& provider) const
{
    // Start with inherited blues (from selected parent chain)
    std::vector<uint256> current_blues = inherited_blues;

    for (const uint256& candidate : mergeset) {
        // Count how many current blues are in the anti-cone of this candidate
        uint32_t anticone = AntiConeBlueCount(candidate, current_blues, provider);
        if (anticone <= m_k) {
            out_blues.push_back(candidate);
            current_blues.push_back(candidate);
        } else {
            out_reds.push_back(candidate);
        }
    }
}

// ---------------------------------------------------------------------------
// GhostdagManager::ComputeGhostdag
// ---------------------------------------------------------------------------
GhostdagData GhostdagManager::ComputeGhostdag(
    const std::vector<uint256>& parents,
    const IGhostdagBlockProvider& provider) const
{
    GhostdagData result;

    if (parents.empty()) {
        // Genesis block
        result.blue_score = 0;
        result.blue_work = 0;
        return result;
    }

    // 1. Select the best parent (highest blue score, tie-break by hash)
    result.selected_parent = SelectBestParent(parents, provider);

    // 2. Get selected parent's GHOSTDAG data
    const GhostdagData* sp_data = provider.GetGhostdagData(result.selected_parent);
    uint64_t sp_blue_score = sp_data ? sp_data->blue_score : 0;
    uint64_t sp_blue_work = sp_data ? sp_data->blue_work : 0;

    // 3. Get the "inherited" blue set from selected parent's chain
    //    For efficiency, we only need the blues from the selected parent itself
    //    (its mergeset blues + its own chain blues are already scored)
    std::vector<uint256> inherited_blues;
    if (sp_data && !sp_data->selected_parent.IsNull()) {
        // Collect blues from selected parent's blue chain (simplified:
        // use selected parent chain blues up to K depth)
        uint256 cur = result.selected_parent;
        uint32_t depth = 0;
        while (!cur.IsNull() && depth < m_k + 1) {
            inherited_blues.push_back(cur);
            const GhostdagData* d = provider.GetGhostdagData(cur);
            if (!d || d->selected_parent.IsNull()) break;
            cur = d->selected_parent;
            ++depth;
        }
    } else {
        inherited_blues.push_back(result.selected_parent);
    }

    // 4. Compute the mergeset
    std::vector<uint256> mergeset = ComputeMergeset(parents, result.selected_parent, provider);

    // 5. Classify mergeset into blues and reds
    ClassifyMergeset(mergeset, inherited_blues, result.mergeset_blues, result.mergeset_reds, provider);

    // 6. Compute blue score: selected parent's score + number of blues in mergeset + 1 (for the block itself if blue)
    result.blue_score = sp_blue_score + static_cast<uint64_t>(result.mergeset_blues.size()) + 1;

    // 7. Compute blue work
    result.blue_work = sp_blue_work;
    for (const uint256& blue : result.mergeset_blues) {
        result.blue_work += provider.GetBlockWork(blue);
    }

    return result;
}

// ---------------------------------------------------------------------------
// GhostdagManager::ComputeVirtual
// ---------------------------------------------------------------------------
GhostdagData GhostdagManager::ComputeVirtual(
    const std::vector<uint256>& tips,
    const IGhostdagBlockProvider& provider) const
{
    return ComputeGhostdag(tips, provider);
}

// ---------------------------------------------------------------------------
// GhostdagManager::TopologicalOrder
// ---------------------------------------------------------------------------
std::vector<uint256> GhostdagManager::TopologicalOrder(
    const std::unordered_set<uint256>& all_blocks,
    const GhostdagData& virtual_data,
    const IGhostdagBlockProvider& provider) const
{
    // Kahn's algorithm: sort by (blue_score, hash) with dependency constraints
    std::unordered_map<uint256, int> in_degree;
    std::unordered_map<uint256, std::vector<uint256>> children;

    for (const uint256& h : all_blocks) {
        if (in_degree.find(h) == in_degree.end()) {
            in_degree[h] = 0;
        }
        std::vector<uint256> pars = provider.GetParents(h);
        for (const uint256& p : pars) {
            if (all_blocks.count(p)) {
                in_degree[h]++;
                children[p].push_back(h);
            }
        }
    }

    // Min-priority queue: prioritize lower blue score, tie-break by hash
    using Entry = std::pair<uint64_t, uint256>;
    std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> pq;

    for (const auto& [h, deg] : in_degree) {
        if (deg == 0) {
            const GhostdagData* d = provider.GetGhostdagData(h);
            uint64_t score = d ? d->blue_score : 0;
            pq.push({score, h});
        }
    }

    std::vector<uint256> order;
    order.reserve(all_blocks.size());

    while (!pq.empty()) {
        auto [score, h] = pq.top();
        pq.pop();
        order.push_back(h);

        for (const uint256& child : children[h]) {
            in_degree[child]--;
            if (in_degree[child] == 0) {
                const GhostdagData* d = provider.GetGhostdagData(child);
                uint64_t cscore = d ? d->blue_score : 0;
                pq.push({cscore, child});
            }
        }
    }

    return order;
}

// ---------------------------------------------------------------------------
// ComputeVirtualSelectedParentChain (free function)
// ---------------------------------------------------------------------------
std::vector<uint256> ComputeVirtualSelectedParentChain(
    const std::vector<uint256>& tips,
    const IGhostdagBlockProvider& provider,
    uint32_t k)
{
    GhostdagManager mgr(k);
    GhostdagData vd = mgr.ComputeVirtual(tips, provider);
    return mgr.SelectBestParent(tips, provider) != uint256{}
        ? std::vector<uint256>({mgr.SelectBestParent(tips, provider)})
        : std::vector<uint256>{};
}

} // namespace dag
