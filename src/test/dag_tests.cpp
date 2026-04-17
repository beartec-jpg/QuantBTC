// Copyright (c) 2026 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <dag/dagtipset.h>
#include <dag/ghostdag.h>
#include <uint256.h>

#include <boost/test/unit_test.hpp>

#include <unordered_map>
#include <vector>

namespace {

/** Deterministic test hash from an integer. */
uint256 MakeHash(unsigned n)
{
    uint256 h;
    *h.begin() = static_cast<uint8_t>(n & 0xff);
    *(h.begin() + 1) = static_cast<uint8_t>((n >> 8) & 0xff);
    return h;
}

// =========================================================================
// Minimal IGhostdagBlockProvider for unit-testing GhostdagManager in
// isolation (no CBlockIndex required).
// =========================================================================
class TestBlockProvider final : public dag::IGhostdagBlockProvider {
public:
    struct BlockInfo {
        dag::GhostdagData ghostdag;
        std::vector<uint256> parents;
        uint64_t work{1};
    };

    void AddBlock(const uint256& hash, const std::vector<uint256>& parents,
                  const dag::GhostdagData& data, uint64_t work = 1)
    {
        m_blocks[hash] = {data, parents, work};
    }

    // Store computed GHOSTDAG result for a block so later queries can use it.
    void StoreGhostdag(const uint256& hash, const dag::GhostdagData& data)
    {
        m_blocks[hash].ghostdag = data;
    }

    const dag::GhostdagData* GetGhostdagData(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        if (it == m_blocks.end()) return nullptr;
        return &it->second.ghostdag;
    }

    std::vector<uint256> GetParents(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        if (it == m_blocks.end()) return {};
        return it->second.parents;
    }

    bool IsAncestorOf(const uint256& ancestor, const uint256& block) const override
    {
        // BFS from block toward parents
        if (ancestor == block) return true;
        std::vector<uint256> queue;
        std::set<uint256> visited;
        queue.push_back(block);
        visited.insert(block);
        size_t front = 0;
        while (front < queue.size()) {
            const uint256& cur = queue[front++];
            auto it = m_blocks.find(cur);
            if (it == m_blocks.end()) continue;
            for (const uint256& p : it->second.parents) {
                if (p == ancestor) return true;
                if (visited.insert(p).second) queue.push_back(p);
            }
        }
        return false;
    }

    uint64_t GetBlockWork(const uint256& hash) const override
    {
        auto it = m_blocks.find(hash);
        if (it == m_blocks.end()) return 0;
        return it->second.work;
    }

private:
    std::map<uint256, BlockInfo> m_blocks;
};

} // namespace

BOOST_AUTO_TEST_SUITE(dag_tests)

// -----------------------------------------------------------------------
// DagTipSet tests
// -----------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(tipset_single_block)
{
    dag::DagTipSet ts;
    BOOST_CHECK_EQUAL(ts.Size(), 0U);

    uint256 genesis = MakeHash(0);
    ts.BlockConnected(genesis, /*blue_score=*/0, /*parents=*/{});
    BOOST_CHECK_EQUAL(ts.Size(), 1U);
    BOOST_CHECK(ts.IsTip(genesis));
}

BOOST_AUTO_TEST_CASE(tipset_parent_removed)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    uint256 block1 = MakeHash(1);

    ts.BlockConnected(genesis, 0, {});
    ts.BlockConnected(block1, 1, {genesis});

    BOOST_CHECK(!ts.IsTip(genesis));
    BOOST_CHECK(ts.IsTip(block1));
    BOOST_CHECK_EQUAL(ts.Size(), 1U);
}

BOOST_AUTO_TEST_CASE(tipset_multiple_tips)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    uint256 a = MakeHash(1);
    uint256 b = MakeHash(2);

    ts.BlockConnected(genesis, 0, {});
    ts.BlockConnected(a, 1, {genesis});
    ts.BlockConnected(b, 1, {genesis});

    // genesis removed by both a and b; a and b are tips
    BOOST_CHECK(!ts.IsTip(genesis));
    BOOST_CHECK(ts.IsTip(a));
    BOOST_CHECK(ts.IsTip(b));
    BOOST_CHECK_EQUAL(ts.Size(), 2U);
}

BOOST_AUTO_TEST_CASE(tipset_mining_parents_ordered)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    uint256 low_score = MakeHash(1);
    uint256 high_score = MakeHash(2);

    ts.BlockConnected(genesis, 0, {});
    ts.BlockConnected(low_score, 5, {genesis});
    ts.BlockConnected(high_score, 10, {genesis});

    auto parents = ts.GetMiningParents(32);
    BOOST_REQUIRE(parents.size() == 2);
    BOOST_CHECK(parents[0] == high_score); // highest score first
    BOOST_CHECK(parents[1] == low_score);
}

BOOST_AUTO_TEST_CASE(tipset_mining_parents_capped)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    ts.BlockConnected(genesis, 0, {});

    for (unsigned i = 1; i <= 10; ++i) {
        ts.BlockConnected(MakeHash(i), i, {genesis});
    }

    auto parents = ts.GetMiningParents(3);
    BOOST_CHECK_EQUAL(parents.size(), 3U);
}

BOOST_AUTO_TEST_CASE(tipset_disconnect_restores_parent)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    uint256 block1 = MakeHash(1);

    ts.BlockConnected(genesis, 0, {});
    ts.BlockConnected(block1, 1, {genesis});
    BOOST_CHECK(!ts.IsTip(genesis));

    ts.BlockDisconnected(block1, {genesis});
    BOOST_CHECK(ts.IsTip(genesis));
    BOOST_CHECK(!ts.IsTip(block1));
}

BOOST_AUTO_TEST_CASE(tipset_disconnect_preserves_score)
{
    dag::DagTipSet ts;
    uint256 genesis = MakeHash(0);
    uint256 a = MakeHash(1);
    uint256 b = MakeHash(2);

    ts.BlockConnected(genesis, 0, {});
    ts.BlockConnected(a, 5, {genesis});
    ts.BlockConnected(b, 10, {genesis});

    // Disconnect b — genesis should be restored with its original score 0
    ts.BlockDisconnected(b, {genesis});

    BOOST_CHECK(ts.IsTip(genesis));
    BOOST_CHECK(ts.IsTip(a));
    BOOST_CHECK_EQUAL(ts.Size(), 2U);

    // Mining parents should list a (score 5) before genesis (score 0)
    auto parents = ts.GetMiningParents(32);
    BOOST_REQUIRE(parents.size() == 2);
    BOOST_CHECK(parents[0] == a);
    BOOST_CHECK(parents[1] == genesis);
}

BOOST_AUTO_TEST_CASE(tipset_clear)
{
    dag::DagTipSet ts;
    ts.BlockConnected(MakeHash(0), 0, {});
    ts.BlockConnected(MakeHash(1), 1, {MakeHash(0)});
    ts.Clear();
    BOOST_CHECK_EQUAL(ts.Size(), 0U);
}

// -----------------------------------------------------------------------
// GhostdagManager tests
// -----------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(ghostdag_genesis)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    auto result_opt = mgr.ComputeGhostdag({}, provider);
    BOOST_REQUIRE(result_opt.has_value());
    const dag::GhostdagData& result = *result_opt;
    BOOST_CHECK_EQUAL(result.blue_score, 0U);
    BOOST_CHECK(result.selected_parent.IsNull());
}

BOOST_AUTO_TEST_CASE(ghostdag_single_parent)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    gen_data.blue_work = 0;
    provider.AddBlock(genesis, {}, gen_data);

    auto result_opt = mgr.ComputeGhostdag({genesis}, provider);
    BOOST_REQUIRE(result_opt.has_value());
    const dag::GhostdagData& result = *result_opt;
    BOOST_CHECK(result.selected_parent == genesis);
    BOOST_CHECK_EQUAL(result.blue_score, 1U); // genesis blue_score + 0 blues in mergeset + 1
    BOOST_CHECK(result.mergeset_blues.empty());
    BOOST_CHECK(result.mergeset_reds.empty());
}

BOOST_AUTO_TEST_CASE(ghostdag_select_best_parent)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 a = MakeHash(1);
    dag::GhostdagData data_a;
    data_a.blue_score = 5;
    provider.AddBlock(a, {}, data_a);

    uint256 b = MakeHash(2);
    dag::GhostdagData data_b;
    data_b.blue_score = 10;
    provider.AddBlock(b, {}, data_b);

    uint256 c = MakeHash(3);
    dag::GhostdagData data_c;
    data_c.blue_score = 10; // tie with b
    provider.AddBlock(c, {}, data_c);

    // b should win over a (higher score)
    uint256 best = mgr.SelectBestParent({a, b}, provider);
    BOOST_CHECK(best == b);

    // Between b and c (same score), lower hash wins
    best = mgr.SelectBestParent({b, c}, provider);
    BOOST_CHECK(best == (b < c ? b : c));
}

BOOST_AUTO_TEST_CASE(ghostdag_mergeset_classification)
{
    // Build a simple diamond: genesis -> A, genesis -> B, then C parents both A and B
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    gen_data.blue_work = 0;
    provider.AddBlock(genesis, {}, gen_data);

    uint256 a = MakeHash(1);
    dag::GhostdagData data_a;
    data_a.blue_score = 1;
    data_a.blue_work = 1;
    data_a.selected_parent = genesis;
    provider.AddBlock(a, {genesis}, data_a);

    uint256 b = MakeHash(2);
    dag::GhostdagData data_b;
    data_b.blue_score = 1;
    data_b.blue_work = 1;
    data_b.selected_parent = genesis;
    provider.AddBlock(b, {genesis}, data_b);

    // Block C with parents A and B
    auto result_opt = mgr.ComputeGhostdag({a, b}, provider);
    BOOST_REQUIRE(result_opt.has_value());
    const dag::GhostdagData& result = *result_opt;

    // The selected parent should be whichever has the lower hash (tie on score=1)
    uint256 expected_sp = (a < b) ? a : b;
    uint256 expected_merge = (a < b) ? b : a;
    BOOST_CHECK(result.selected_parent == expected_sp);

    // The other should appear in the mergeset blues (anticone size <= K=18)
    BOOST_CHECK_EQUAL(result.mergeset_blues.size(), 1U);
    BOOST_CHECK(result.mergeset_blues[0] == expected_merge);
    BOOST_CHECK(result.mergeset_reds.empty());

    // Blue score = selected_parent.blue_score (1) + mergeset_blues (1) + 1 = 3
    BOOST_CHECK_EQUAL(result.blue_score, 3U);
}

BOOST_AUTO_TEST_CASE(ghostdag_virtual)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    provider.AddBlock(genesis, {}, gen_data);

    // ComputeVirtual with single tip = same as ComputeGhostdag
    auto vd_opt = mgr.ComputeVirtual({genesis}, provider);
    BOOST_REQUIRE(vd_opt.has_value());
    const dag::GhostdagData& vd = *vd_opt;
    BOOST_CHECK(vd.selected_parent == genesis);
    BOOST_CHECK_EQUAL(vd.blue_score, 1U);
}

BOOST_AUTO_TEST_CASE(virtual_selected_parent_chain)
{
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    // genesis has no selected parent (IsNull())
    provider.AddBlock(genesis, {}, gen_data);

    uint256 a = MakeHash(1);
    dag::GhostdagData data_a;
    data_a.blue_score = 1;
    data_a.selected_parent = genesis;
    provider.AddBlock(a, {genesis}, data_a);

    auto chain = dag::ComputeVirtualSelectedParentChain({a}, provider, 18);
    // The virtual block's selected parent is 'a'; 'a's selected parent is
    // genesis; genesis has no selected parent.  The full chain is [a, genesis].
    BOOST_REQUIRE_EQUAL(chain.size(), 2U);
    BOOST_CHECK(chain[0] == a);      // virtual's selected parent
    BOOST_CHECK(chain[1] == genesis); // a's selected parent
}

BOOST_AUTO_TEST_CASE(virtual_selected_parent_chain_max_depth)
{
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    provider.AddBlock(genesis, {}, gen_data);

    uint256 a = MakeHash(1);
    dag::GhostdagData data_a;
    data_a.blue_score = 1;
    data_a.selected_parent = genesis;
    provider.AddBlock(a, {genesis}, data_a);

    // max_depth=1 should cap the walk at one entry
    auto chain = dag::ComputeVirtualSelectedParentChain({a}, provider, 18, /*max_depth=*/1);
    BOOST_REQUIRE_EQUAL(chain.size(), 1U);
    BOOST_CHECK(chain[0] == a);
}

// -----------------------------------------------------------------------
// Topological ordering test
// -----------------------------------------------------------------------

BOOST_AUTO_TEST_CASE(topological_order_simple)
{
    dag::GhostdagManager mgr(18);
    TestBlockProvider provider;

    uint256 genesis = MakeHash(0);
    dag::GhostdagData gen_data;
    gen_data.blue_score = 0;
    provider.AddBlock(genesis, {}, gen_data);

    uint256 a = MakeHash(1);
    dag::GhostdagData data_a;
    data_a.blue_score = 1;
    data_a.selected_parent = genesis;
    provider.AddBlock(a, {genesis}, data_a);

    std::unordered_set<uint256, BlockHasher> all{genesis, a};
    dag::GhostdagData vd;
    vd.selected_parent = a;
    vd.blue_score = 2;

    auto order = mgr.TopologicalOrder(all, vd, provider);
    BOOST_REQUIRE_EQUAL(order.size(), 2U);
    BOOST_CHECK(order[0] == genesis); // genesis first (lower blue score)
    BOOST_CHECK(order[1] == a);
}

BOOST_AUTO_TEST_SUITE_END()
