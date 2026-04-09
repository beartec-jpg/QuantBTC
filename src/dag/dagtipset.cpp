// Copyright (c) 2026 BearTec / QuantumBTC
// Copyright (c) 2024 The QuantumBTC developers
// BearTec original additions in this file are licensed under the
// Business Source License 1.1 until 2030-04-09, after which the
// Change License is MIT. See LICENSE-BUSL and NOTICE.

#include <dag/dagtipset.h>

#include <algorithm>
#include <logging.h>

namespace dag {

void DagTipSet::InsertTip(const uint256& hash, uint64_t blue_score)
{
    m_score_to_hash.emplace(blue_score, hash);
    m_hash_to_score[hash] = blue_score;
    m_known_scores[hash] = blue_score;
}

void DagTipSet::RemoveTip(const uint256& hash)
{
    auto it = m_hash_to_score.find(hash);
    if (it == m_hash_to_score.end()) return;
    uint64_t score = it->second;
    m_score_to_hash.erase({score, hash});
    m_hash_to_score.erase(it);
}

void DagTipSet::BlockConnected(const uint256& block_hash, uint64_t blue_score,
                               const std::vector<uint256>& parents)
{
    size_t before = m_score_to_hash.size();
    // Remove each parent from tips (they now have a child)
    for (const uint256& p : parents) {
        RemoveTip(p);
    }
    // Add the new block as a tip
    InsertTip(block_hash, blue_score);

    // Prune m_known_scores to prevent unbounded growth.
    PruneKnownScores(blue_score);

    LogPrint(BCLog::VALIDATION,
             "DagTipSet::BlockConnected %s score=%u parents=%u tips: %u -> %u\n",
             block_hash.ToString().substr(0, 16), blue_score,
             parents.size(), before, m_score_to_hash.size());
}

void DagTipSet::BlockDisconnected(const uint256& block_hash,
                                  const std::vector<uint256>& parent_hashes)
{
    size_t before = m_score_to_hash.size();
    // Remove the disconnected block from tips
    RemoveTip(block_hash);
    // Re-add parents as tips (they are now childless again) only when we know
    // their score; avoid corrupting order with a synthetic score=0.
    for (const uint256& p : parent_hashes) {
        if (p.IsNull() || m_hash_to_score.find(p) != m_hash_to_score.end()) {
            continue;
        }
        auto known = m_known_scores.find(p);
        if (known != m_known_scores.end()) {
            InsertTip(p, known->second);
            continue;
        }
        LogPrint(BCLog::VALIDATION,
                 "DagTipSet::BlockDisconnected skipping parent %s due to unknown blue_score\n",
                 p.ToString().substr(0, 16));
    }
    LogPrint(BCLog::VALIDATION,
             "DagTipSet::BlockDisconnected %s parents=%u tips: %u -> %u\n",
             block_hash.ToString().substr(0, 16), parent_hashes.size(),
             before, m_score_to_hash.size());
}

std::vector<uint256> DagTipSet::GetMiningParents(uint32_t max_parents) const
{
    std::vector<uint256> result;
    result.reserve(std::min<size_t>(m_score_to_hash.size(), max_parents));
    for (const auto& [score, hash] : m_score_to_hash) {
        if (result.size() >= max_parents) break;
        result.push_back(hash);
    }
    return result;
}

bool DagTipSet::IsTip(const uint256& hash) const
{
    return m_hash_to_score.count(hash) > 0;
}

void DagTipSet::Clear()
{
    m_score_to_hash.clear();
    m_hash_to_score.clear();
    m_known_scores.clear();
}

void DagTipSet::PruneKnownScores(uint64_t best_score)
{
    if (best_score <= KNOWN_SCORES_PRUNE_DEPTH) return;
    uint64_t cutoff = best_score - KNOWN_SCORES_PRUNE_DEPTH;
    for (auto it = m_known_scores.begin(); it != m_known_scores.end(); ) {
        if (it->second < cutoff && m_hash_to_score.find(it->first) == m_hash_to_score.end()) {
            it = m_known_scores.erase(it);
        } else {
            ++it;
        }
    }
}

} // namespace dag
