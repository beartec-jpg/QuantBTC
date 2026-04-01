// Copyright (c) 2026 beartec-jpg / QuantumBTC
// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <dag/dagtipset.h>

#include <algorithm>
#include <logging.h>

namespace dag {

void DagTipSet::InsertTip(const uint256& hash, uint64_t blue_score)
{
    m_score_to_hash.emplace(blue_score, hash);
    m_hash_to_score[hash] = blue_score;
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
    // Re-add parents as tips (they are now childless again).
    // We insert with score 0 as a fallback; the correct score will be
    // set if/when the parent is later re-selected via BlockConnected.
    for (const uint256& p : parent_hashes) {
        if (!p.IsNull() && m_hash_to_score.find(p) == m_hash_to_score.end()) {
            InsertTip(p, 0);
        }
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
}

} // namespace dag
