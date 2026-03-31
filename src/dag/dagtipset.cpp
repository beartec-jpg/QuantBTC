// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <dag/dagtipset.h>

#include <algorithm>

namespace dag {

void DagTipSet::BlockConnected(const uint256& block_hash, const std::vector<uint256>& parents)
{
    // Remove each parent from tips (they now have a child)
    for (const uint256& p : parents) {
        m_tips.erase(p);
    }
    // Add the new block as a tip
    m_tips.insert(block_hash);
}

void DagTipSet::BlockDisconnected(const uint256& block_hash, const std::vector<uint256>& parents)
{
    // Remove the disconnected block from tips
    m_tips.erase(block_hash);
    // Re-add its parents as tips (they may now be childless again)
    for (const uint256& p : parents) {
        if (!p.IsNull()) {
            m_tips.insert(p);
        }
    }
}

std::vector<uint256> DagTipSet::GetMiningParents(uint32_t max_parents) const
{
    std::vector<uint256> result;
    result.reserve(std::min<size_t>(m_tips.size(), max_parents));
    for (const uint256& tip : m_tips) {
        if (result.size() >= max_parents) break;
        result.push_back(tip);
    }
    return result;
}

bool DagTipSet::IsTip(const uint256& hash) const
{
    return m_tips.count(hash) > 0;
}

void DagTipSet::Clear()
{
    m_tips.clear();
}

} // namespace dag
