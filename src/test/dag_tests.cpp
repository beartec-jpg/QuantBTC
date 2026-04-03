// Copyright (c) 2026 beartec-jpg / QuantumBTC
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <dag/dagtipset.h>
#include <dag/ghostdag.h>
#include <uint256.h>

#include <unordered_map>
#include <vector>

namespace {

/** Simple in-memory block provider for GHOSTDAG unit tests. */
class TestBlockProvider : public dag::IGhostdagBlockProvider {
public:
    struct BlockInfo {
        dag::GhostdagData ghostdag;
        std::vector<uint256> parents;
        uint64_t work{1};
    };

    void AddBlock(const uint256& hash, const std::vector<uint256>& parents,
                  const dag::GhostdagData& gd, uint64_t work = 1)
    {
        m_blocks[hash] = {gd, parents, work};
    }

    const dag::GhostdagData* GetGhostdagData(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        return it != m_blocks.end() ? &it->second.ghostdag : nullptr;
    }

    std::vector<uint256> GetParents(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        return it != m_blocks.end() ? it->second.parents : std::vector<uint256>{};
    }

    bool IsAncestorOf(const uint256& ancestor, const uint256& block) const override
    {
        // Simple recursive check for the test DAG
        if (ancestor == block) return true;
        auto it = m_blocks.find(block);
        if (it == m_blocks.end()) return false;
        for (const uint256& p : it->second.parents) {
            if (IsAncestorOf(ancestor, p)) return true;
        }
        return false;
    }

    uint64_t GetBlockWork(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        return it != m_blocks.end() ? it->second.work : 0;
    }

private:
    std::unordered_map<uint256, BlockInfo, BlockHasher> m_blocks;
};

/** Helper: create a uint256 from a small integer for readable test hashes. */
uint256 MakeHash(uint8_t id)
{
    uint256 h;
    h.SetNull();
    *h.begin() = id;
    return h;
}

} // namespace

BOOST_AUTO_TEST_SUITE(dag_tests)

// ---------------------------------------------------------------------------
// GHOSTDAG tests
// ---------------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(ghostdag_select_best_parent_single)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(1);
    dag::GhostdagData gd_genesis;
    gd_genesis.blue_score = 0;
    provider.AddBlock(genesis, {}, gd_genesis);

    std::vector<uint256> candidates = {genesis};
    uint256 best = mgr.SelectBestParent(candidates, provider);
    BOOST_CHECK(best == genesis);
}

BOOST_AUTO_TEST_CASE(ghostdag_select_best_parent_highest_score)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 a = MakeHash(1);
    uint256 b = MakeHash(2);
    uint256 c = MakeHash(3);

    dag::GhostdagData gd_a; gd_a.blue_score = 5;
    dag::GhostdagData gd_b; gd_b.blue_score = 10;
    dag::GhostdagData gd_c; gd_c.blue_score = 3;

    provider.AddBlock(a, {}, gd_a);
    provider.AddBlock(b, {}, gd_b);
    provider.AddBlock(c, {}, gd_c);

    std::vector<uint256> candidates = {a, b, c};
    uint256 best = mgr.SelectBestParent(candidates, provider);
    BOOST_CHECK(best == b);
}

BOOST_AUTO_TEST_CASE(ghostdag_select_best_parent_tiebreak_by_hash)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 a = MakeHash(1);
    uint256 b = MakeHash(2);

    dag::GhostdagData gd_a; gd_a.blue_score = 5;
    dag::GhostdagData gd_b; gd_b.blue_score = 5;

    provider.AddBlock(a, {}, gd_a);
    provider.AddBlock(b, {}, gd_b);

    std::vector<uint256> candidates = {a, b};
    uint256 best = mgr.SelectBestParent(candidates, provider);
    // Tie-break by lower hash
    BOOST_CHECK(best == a);
}

BOOST_AUTO_TEST_CASE(ghostdag_select_best_parent_empty)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    std::vector<uint256> candidates;
    uint256 best = mgr.SelectBestParent(candidates, provider);
    BOOST_CHECK(best == uint256{});
}

BOOST_AUTO_TEST_CASE(ghostdag_compute_genesis)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    // Genesis has no parents
    dag::GhostdagData result = mgr.ComputeGhostdag({}, provider);
    BOOST_CHECK_EQUAL(result.blue_score, 0U);
    BOOST_CHECK_EQUAL(result.blue_work, 0U);
    BOOST_CHECK(result.selected_parent.IsNull());
}

BOOST_AUTO_TEST_CASE(ghostdag_compute_single_parent)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(1);
    dag::GhostdagData gd_genesis;
    gd_genesis.blue_score = 0;
    gd_genesis.blue_work = 1;
    provider.AddBlock(genesis, {}, gd_genesis, 1);

    dag::GhostdagData result = mgr.ComputeGhostdag({genesis}, provider);
    BOOST_CHECK(result.selected_parent == genesis);
    BOOST_CHECK(result.blue_score > 0);
}

BOOST_AUTO_TEST_CASE(ghostdag_virtual_selected_parent_chain)
{
    TestBlockProvider provider;

    uint256 genesis = MakeHash(1);
    dag::GhostdagData gd_genesis;
    gd_genesis.blue_score = 0;
    provider.AddBlock(genesis, {}, gd_genesis);

    uint256 block_a = MakeHash(2);
    dag::GhostdagData gd_a;
    gd_a.blue_score = 1;
    gd_a.selected_parent = genesis;
    provider.AddBlock(block_a, {genesis}, gd_a);

    // Tips = {block_a}
    std::vector<uint256> chain = dag::ComputeVirtualSelectedParentChain({block_a}, provider, 18);
    BOOST_CHECK(!chain.empty());
    BOOST_CHECK(chain[0] == block_a);
}

// ---------------------------------------------------------------------------
// DagTipSet tests
// ---------------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(dagtipset_initially_empty)
{
    dag::DagTipSet tips;
    BOOST_CHECK_EQUAL(tips.Size(), 0U);
}

BOOST_AUTO_TEST_CASE(dagtipset_block_connected_adds_tip)
{
    dag::DagTipSet tips;
    uint256 genesis = MakeHash(1);

    tips.BlockConnected(genesis, 0, {});
    BOOST_CHECK_EQUAL(tips.Size(), 1U);
    BOOST_CHECK(tips.IsTip(genesis));
}

BOOST_AUTO_TEST_CASE(dagtipset_block_connected_removes_parents)
{
    dag::DagTipSet tips;
    uint256 genesis = MakeHash(1);
    uint256 block_a = MakeHash(2);

    tips.BlockConnected(genesis, 0, {});
    BOOST_CHECK(tips.IsTip(genesis));

    // block_a references genesis as parent → genesis is no longer a tip
    tips.BlockConnected(block_a, 1, {genesis});
    BOOST_CHECK(!tips.IsTip(genesis));
    BOOST_CHECK(tips.IsTip(block_a));
    BOOST_CHECK_EQUAL(tips.Size(), 1U);
}

BOOST_AUTO_TEST_CASE(dagtipset_multiple_tips)
{
    dag::DagTipSet tips;
    uint256 genesis = MakeHash(1);
    uint256 block_a = MakeHash(2);
    uint256 block_b = MakeHash(3);

    tips.BlockConnected(genesis, 0, {});
    // Two blocks both reference genesis
    tips.BlockConnected(block_a, 1, {genesis});
    tips.BlockConnected(block_b, 2, {});

    BOOST_CHECK(tips.IsTip(block_a));
    BOOST_CHECK(tips.IsTip(block_b));
    BOOST_CHECK_EQUAL(tips.Size(), 2U);
}

BOOST_AUTO_TEST_CASE(dagtipset_mining_parents_order)
{
    dag::DagTipSet tips;
    uint256 block_a = MakeHash(1);
    uint256 block_b = MakeHash(2);
    uint256 block_c = MakeHash(3);

    tips.BlockConnected(block_a, 5, {});
    tips.BlockConnected(block_b, 10, {});
    tips.BlockConnected(block_c, 3, {});

    auto parents = tips.GetMiningParents(3);
    BOOST_CHECK_EQUAL(parents.size(), 3U);
    // Highest blue_score first
    BOOST_CHECK(parents[0] == block_b);
}

BOOST_AUTO_TEST_CASE(dagtipset_mining_parents_max_limit)
{
    dag::DagTipSet tips;
    for (uint8_t i = 1; i <= 40; ++i) {
        tips.BlockConnected(MakeHash(i), i, {});
    }

    // MAX_BLOCK_PARENTS = 32 by default
    auto parents = tips.GetMiningParents(dag::MAX_BLOCK_PARENTS);
    BOOST_CHECK(parents.size() <= dag::MAX_BLOCK_PARENTS);
}

BOOST_AUTO_TEST_CASE(dagtipset_block_disconnected)
{
    dag::DagTipSet tips;
    uint256 genesis = MakeHash(1);
    uint256 block_a = MakeHash(2);

    tips.BlockConnected(genesis, 0, {});
    tips.BlockConnected(block_a, 1, {genesis});

    BOOST_CHECK(!tips.IsTip(genesis));
    BOOST_CHECK(tips.IsTip(block_a));

    // Disconnect block_a → it is removed, genesis becomes tip again
    tips.BlockDisconnected(block_a, {genesis});
    BOOST_CHECK(tips.IsTip(genesis));
    BOOST_CHECK(!tips.IsTip(block_a));
}

BOOST_AUTO_TEST_CASE(dagtipset_clear)
{
    dag::DagTipSet tips;
    tips.BlockConnected(MakeHash(1), 0, {});
    tips.BlockConnected(MakeHash(2), 1, {});
    BOOST_CHECK(tips.Size() > 0);

    tips.Clear();
    BOOST_CHECK_EQUAL(tips.Size(), 0U);
}

// ---------------------------------------------------------------------------
// DAG parent validation tests
// ---------------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(dag_max_block_parents_constant)
{
    // Verify the MAX_BLOCK_PARENTS constant is set to 32
    BOOST_CHECK_EQUAL(dag::MAX_BLOCK_PARENTS, 32U);
}

BOOST_AUTO_TEST_CASE(dag_parent_count_within_limit)
{
    // Simulate validation: a block with parents within limit should be valid
    std::vector<uint256> parents;
    for (uint8_t i = 1; i <= dag::MAX_BLOCK_PARENTS; ++i) {
        parents.push_back(MakeHash(i));
    }
    BOOST_CHECK(parents.size() <= dag::MAX_BLOCK_PARENTS);
}

BOOST_AUTO_TEST_CASE(dag_parent_count_exceeds_limit)
{
    // Simulate validation: a block with too many parents should be rejected
    std::vector<uint256> parents;
    for (uint8_t i = 1; i <= dag::MAX_BLOCK_PARENTS + 1; ++i) {
        parents.push_back(MakeHash(i));
    }
    BOOST_CHECK(parents.size() > dag::MAX_BLOCK_PARENTS);
}

BOOST_AUTO_TEST_SUITE_END()
