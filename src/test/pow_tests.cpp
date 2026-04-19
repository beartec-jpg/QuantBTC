// Copyright (c) 2015-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <chain.h>
#include <chainparams.h>
#include <pow.h>
#include <test/util/random.h>
#include <test/util/setup_common.h>
#include <util/chaintype.h>

#include <boost/test/unit_test.hpp>

BOOST_FIXTURE_TEST_SUITE(pow_tests, BasicTestingSetup)

/* Test calculation of next difficulty target with no constraints applying */
BOOST_AUTO_TEST_CASE(get_next_work)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1261130161; // Block #30240
    CBlockIndex pindexLast;
    pindexLast.nHeight = 32255;
    pindexLast.nTime = 1262152739;  // Block #32255
    pindexLast.nBits = 0x1d00ffff;

    // Here (and below): expected_nbits is calculated in
    // CalculateNextWorkRequired(); redoing the calculation here would be just
    // reimplementing the same code that is written in pow.cpp. Rather than
    // copy that code, we just hardcode the expected result.
    unsigned int expected_nbits = 0x1d00d86aU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
}

/* Test the constraint on the upper bound for next work */
BOOST_AUTO_TEST_CASE(get_next_work_pow_limit)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1231006505; // Block #0
    CBlockIndex pindexLast;
    pindexLast.nHeight = 2015;
    pindexLast.nTime = 1233061996;  // Block #2015
    pindexLast.nBits = 0x1d00ffff;
    unsigned int expected_nbits = 0x1d00ffffU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
}

/* Test the constraint on the lower bound for actual time taken */
BOOST_AUTO_TEST_CASE(get_next_work_lower_limit_actual)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1279008237; // Block #66528
    CBlockIndex pindexLast;
    pindexLast.nHeight = 68543;
    pindexLast.nTime = 1279297671;  // Block #68543
    pindexLast.nBits = 0x1c05a3f4;
    unsigned int expected_nbits = 0x1c0168fdU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
    // Test that reducing nbits further would not be a PermittedDifficultyTransition.
    unsigned int invalid_nbits = expected_nbits-1;
    BOOST_CHECK(!PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, invalid_nbits));
}

/* Test the constraint on the upper bound for actual time taken */
BOOST_AUTO_TEST_CASE(get_next_work_upper_limit_actual)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    int64_t nLastRetargetTime = 1263163443; // NOTE: Not an actual block time
    CBlockIndex pindexLast;
    pindexLast.nHeight = 46367;
    pindexLast.nTime = 1269211443;  // Block #46367
    pindexLast.nBits = 0x1c387f6f;
    unsigned int expected_nbits = 0x1d00e1fdU;
    BOOST_CHECK_EQUAL(CalculateNextWorkRequired(&pindexLast, nLastRetargetTime, chainParams->GetConsensus()), expected_nbits);
    BOOST_CHECK(PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, expected_nbits));
    // Test that increasing nbits further would not be a PermittedDifficultyTransition.
    unsigned int invalid_nbits = expected_nbits+1;
    BOOST_CHECK(!PermittedDifficultyTransition(chainParams->GetConsensus(), pindexLast.nHeight+1, pindexLast.nBits, invalid_nbits));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_negative_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    nBits = UintToArith256(consensus.powLimit).GetCompact(true);
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_overflow_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits{~0x00800000U};
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_too_easy_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 nBits_arith = UintToArith256(consensus.powLimit);
    nBits_arith *= 2;
    nBits = nBits_arith.GetCompact();
    hash = uint256{1};
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_biger_hash_than_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 hash_arith = UintToArith256(consensus.powLimit);
    nBits = hash_arith.GetCompact();
    hash_arith *= 2; // hash > nBits
    hash = ArithToUint256(hash_arith);
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(CheckProofOfWork_test_zero_target)
{
    const auto consensus = CreateChainParams(*m_node.args, ChainType::MAIN)->GetConsensus();
    uint256 hash;
    unsigned int nBits;
    arith_uint256 hash_arith{0};
    nBits = hash_arith.GetCompact();
    hash = ArithToUint256(hash_arith);
    BOOST_CHECK(!CheckProofOfWork(hash, nBits, consensus));
}

BOOST_AUTO_TEST_CASE(GetBlockProofEquivalentTime_test)
{
    const auto chainParams = CreateChainParams(*m_node.args, ChainType::MAIN);
    std::vector<CBlockIndex> blocks(10000);
    for (int i = 0; i < 10000; i++) {
        blocks[i].pprev = i ? &blocks[i - 1] : nullptr;
        blocks[i].nHeight = i;
        blocks[i].nTime = 1269211443 + i * chainParams->GetConsensus().nPowTargetSpacing;
        blocks[i].nBits = 0x207fffff; /* target 0x7fffff000... */
        blocks[i].nChainWork = i ? blocks[i - 1].nChainWork + GetBlockProof(blocks[i - 1]) : arith_uint256(0);
    }

    for (int j = 0; j < 1000; j++) {
        CBlockIndex *p1 = &blocks[InsecureRandRange(10000)];
        CBlockIndex *p2 = &blocks[InsecureRandRange(10000)];
        CBlockIndex *p3 = &blocks[InsecureRandRange(10000)];

        int64_t tdiff = GetBlockProofEquivalentTime(*p1, *p2, *p3, chainParams->GetConsensus());
        BOOST_CHECK_EQUAL(tdiff, p1->GetBlockTime() - p2->GetBlockTime());
    }
}

void sanity_check_chainparams(const ArgsManager& args, ChainType chain_type)
{
    const auto chainParams = CreateChainParams(args, chain_type);
    const auto consensus = chainParams->GetConsensus();

    // hash genesis is correct
    BOOST_CHECK_EQUAL(consensus.hashGenesisBlock, chainParams->GenesisBlock().GetHash());

    // target timespan is an even multiple of spacing
    BOOST_CHECK_EQUAL(consensus.nPowTargetTimespan % consensus.nPowTargetSpacing, 0);

    // genesis nBits is positive, doesn't overflow and is lower than powLimit
    arith_uint256 pow_compact;
    bool neg, over;
    pow_compact.SetCompact(chainParams->GenesisBlock().nBits, &neg, &over);
    BOOST_CHECK(!neg && pow_compact != 0);
    BOOST_CHECK(!over);
    BOOST_CHECK(UintToArith256(consensus.powLimit) >= pow_compact);

    // check max target * 4*nPowTargetTimespan doesn't overflow -- see pow.cpp:CalculateNextWorkRequired()
    if (!consensus.fPowNoRetargeting) {
        arith_uint256 targ_max{UintToArith256(uint256{"FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"})};
        targ_max /= consensus.nPowTargetTimespan*4;
        BOOST_CHECK(UintToArith256(consensus.powLimit) < targ_max);
    }
}

BOOST_AUTO_TEST_CASE(ChainParams_MAIN_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::MAIN);
}

BOOST_AUTO_TEST_CASE(ChainParams_REGTEST_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::REGTEST);
}

BOOST_AUTO_TEST_CASE(ChainParams_TESTNET_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::TESTNET);
}

BOOST_AUTO_TEST_CASE(ChainParams_TESTNET4_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::TESTNET4);
}

BOOST_AUTO_TEST_CASE(ChainParams_SIGNET_sanity)
{
    sanity_check_chainparams(*m_node.args, ChainType::SIGNET);
}

/**
 * Test the transaction-load-aware difficulty adjustment in DAG mode.
 *
 * The DAG retarget window is 4032 blocks; the first real retarget fires at
 * height 8063 (the second full window, since the first 4032 blocks bootstrap
 * at powLimit).  pindexFirst for that retarget is at height 4032.
 *
 * With blocks[i].m_chain_tx_count = i * tx_per_block the average tx rate
 * over the window equals exactly tx_per_block:
 *   avg = (chain_tx[8063] - chain_tx[4032]) / 4031
 *       = (8063 - 4032) * tx_per_block / 4031
 *       = 4031 * tx_per_block / 4031 = tx_per_block
 */
BOOST_AUTO_TEST_CASE(dag_load_aware_difficulty_v2_sqrt)
{
    // Build a minimal Consensus::Params with DAG + load-aware difficulty enabled.
    Consensus::Params params;
    params.powLimit                     = uint256{"7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"};
    params.fPowNoRetargeting            = false;
    params.fPowAllowMinDifficultyBlocks = false;
    params.fDagMode                     = true;
    params.nDagTargetSpacingMs          = 1000; // 1-second blocks
    params.nLoadDiffBaseline            = 100;  // 100 tx/block threshold
    params.nLoadDiffMaxMultiplier       = 8;    // cap at 8× harder under sustained attack

    // Build a chain of 8064 blocks (height 0 … 8063) spaced 1 second apart.
    const int CHAIN_HEIGHT = 8064;
    std::vector<CBlockIndex> blocks(CHAIN_HEIGHT);
    for (int i = 0; i < CHAIN_HEIGHT; i++) {
        blocks[i].pprev            = i ? &blocks[i - 1] : nullptr;
        blocks[i].nHeight          = i;
        blocks[i].nTime            = 1700000000 + i; // 1 second per block
        blocks[i].nBits            = 0x207fffff;
        blocks[i].m_chain_tx_count = 0;
    }

    CBlockHeader next_header;
    next_header.nTime = blocks[CHAIN_HEIGHT - 1].nTime + 1;

    const CBlockIndex* pindexLast = &blocks[CHAIN_HEIGHT - 1]; // height 8063

    auto set_tx_rate = [&](int64_t tx_per_block) {
        for (int i = 0; i < CHAIN_HEIGHT; i++) {
            blocks[i].m_chain_tx_count = static_cast<uint64_t>(i) * tx_per_block;
        }
    };

    set_tx_rate(0);
    const unsigned int base_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 base_target;
    base_target.SetCompact(base_bits);

    // Baseline traffic leaves time-based difficulty unchanged.
    set_tx_rate(params.nLoadDiffBaseline);
    BOOST_CHECK_EQUAL(GetNextWorkRequiredDAG(pindexLast, &next_header, params), base_bits);

    // 2× baseline should harden, but more gently than the old linear ramp.
    set_tx_rate(params.nLoadDiffBaseline * 2);
    const unsigned int gentle_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 gentle_target;
    gentle_target.SetCompact(gentle_bits);
    BOOST_CHECK(gentle_target < base_target);

    // 4× baseline and 16× baseline should keep hardening monotonically.
    set_tx_rate(params.nLoadDiffBaseline * 4);
    const unsigned int two_x_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 two_x_target;
    two_x_target.SetCompact(two_x_bits);
    BOOST_CHECK(two_x_target < gentle_target);

    set_tx_rate(params.nLoadDiffBaseline * 16);
    const unsigned int four_x_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 four_x_target;
    four_x_target.SetCompact(four_x_bits);
    BOOST_CHECK(four_x_target < two_x_target);

    // At 64× baseline, sqrt(64)=8 reaches the configured cap.
    set_tx_rate(params.nLoadDiffBaseline * 64);
    const unsigned int cap_threshold_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 cap_threshold_target;
    cap_threshold_target.SetCompact(cap_threshold_bits);
    BOOST_CHECK(cap_threshold_target < four_x_target);

    // Extreme spam should not harden beyond the 8× cap.
    set_tx_rate(params.nLoadDiffBaseline * 100);
    const unsigned int capped_bits = GetNextWorkRequiredDAG(pindexLast, &next_header, params);
    arith_uint256 capped_target;
    capped_target.SetCompact(capped_bits);
    BOOST_CHECK_EQUAL(capped_bits, cap_threshold_bits);
    BOOST_CHECK(capped_target == cap_threshold_target);

    // Feature disabled → identical to pure time-based retarget.
    Consensus::Params params_disabled = params;
    params_disabled.nLoadDiffBaseline = 0;
    set_tx_rate(params.nLoadDiffBaseline * 100);
    BOOST_CHECK_EQUAL(GetNextWorkRequiredDAG(pindexLast, &next_header, params_disabled), base_bits);
}

/**
 * Test the dual-EMA per-block difficulty adjustment.
 *
 * Build chains with different block-time patterns and verify that the
 * fast EMA causes difficulty to rise when blocks are too fast, and ease
 * when blocks are too slow.
 */
BOOST_AUTO_TEST_CASE(dag_dual_ema_difficulty)
{
    Consensus::Params params;
    params.powLimit                     = uint256{"7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"};
    params.fPowNoRetargeting            = false;
    params.fPowAllowMinDifficultyBlocks = false;
    params.fDagMode                     = true;
    params.nDagTargetSpacingMs          = 10000; // 10-second target
    params.nDagDiffWindowSize           = 128;   // max lookback
    params.fDagUseEma                   = true;
    params.nDagEmaFastHalfLife          = 12;
    params.nDagEmaSlowHalfLife          = 72;
    params.nDagEmaMaxAdjust             = 3000;  // max 3× per block
    params.nLoadDiffBaseline            = 0;     // disable load-aware for this test
    params.nLoadDiffMaxMultiplier       = 1;

    const int CHAIN_LEN = 200;
    std::vector<CBlockIndex> blocks(CHAIN_LEN);

    // Helper: build a chain with uniform block spacing
    // Use a mid-range difficulty so there's headroom to go both harder and easier.
    const uint32_t midBits = 0x1f0fffff;
    auto build_uniform_chain = [&](int spacing_sec) {
        for (int i = 0; i < CHAIN_LEN; i++) {
            blocks[i].pprev  = i ? &blocks[i - 1] : nullptr;
            blocks[i].nHeight = i;
            blocks[i].nTime  = 1700000000 + i * spacing_sec;
            blocks[i].nBits  = midBits;
            blocks[i].m_chain_tx_count = 0;
        }
    };

    CBlockHeader next_header;

    // ── 1. On-target blocks (10s each): difficulty should stay roughly the same
    build_uniform_chain(10);
    next_header.nTime = blocks[CHAIN_LEN - 1].nTime + 10;
    const unsigned int on_target_bits = GetNextWorkRequiredDAG(&blocks[CHAIN_LEN - 1], &next_header, params);
    arith_uint256 on_target;
    on_target.SetCompact(on_target_bits);
    arith_uint256 midTarget;
    midTarget.SetCompact(midBits);
    arith_uint256 powLimit = UintToArith256(params.powLimit);
    // Should be very close to the starting target (EMA converges, adjustment ≈ 1.0)
    BOOST_CHECK(on_target <= midTarget);
    BOOST_CHECK(on_target > midTarget / 2);

    // ── 2. Fast blocks (2s each, 5x too fast): difficulty should increase (lower target)
    build_uniform_chain(2);
    next_header.nTime = blocks[CHAIN_LEN - 1].nTime + 2;
    const unsigned int fast_bits = GetNextWorkRequiredDAG(&blocks[CHAIN_LEN - 1], &next_header, params);
    arith_uint256 fast_target;
    fast_target.SetCompact(fast_bits);
    BOOST_CHECK(fast_target < on_target); // harder than on-target

    // ── 3. Slow blocks (30s each, 3x too slow): difficulty should decrease (higher target)
    build_uniform_chain(30);
    next_header.nTime = blocks[CHAIN_LEN - 1].nTime + 30;
    const unsigned int slow_bits = GetNextWorkRequiredDAG(&blocks[CHAIN_LEN - 1], &next_header, params);
    arith_uint256 slow_target;
    slow_target.SetCompact(slow_bits);
    BOOST_CHECK(slow_target > on_target); // easier than on-target

    // ── 4. Spike: 180 blocks at 10s, then 20 blocks at 1s — fast EMA should react
    for (int i = 0; i < CHAIN_LEN; i++) {
        blocks[i].pprev  = i ? &blocks[i - 1] : nullptr;
        blocks[i].nHeight = i;
        int spacing = (i >= 180) ? 1 : 10; // spike at block 180
        blocks[i].nTime  = (i == 0) ? 1700000000 : blocks[i-1].nTime + spacing;
        blocks[i].nBits  = midBits;
        blocks[i].m_chain_tx_count = 0;
    }
    next_header.nTime = blocks[CHAIN_LEN - 1].nTime + 1;
    const unsigned int spike_bits = GetNextWorkRequiredDAG(&blocks[CHAIN_LEN - 1], &next_header, params);
    arith_uint256 spike_target;
    spike_target.SetCompact(spike_bits);
    // After 20 blocks at 1s, fast EMA should have pulled difficulty up (target down)
    BOOST_CHECK(spike_target < on_target);

    // ── 5. Very early chain (height < emaActivation): should return powLimit
    //    emaActivation = max(4, nDagDiffWindowSize) = 128
    build_uniform_chain(10);
    const int emaActivation = std::max(4, static_cast<int>(params.nDagDiffWindowSize));
    next_header.nTime = blocks[emaActivation].nTime + 10;
    const unsigned int early_bits = GetNextWorkRequiredDAG(&blocks[emaActivation - 1], &next_header, params);
    BOOST_CHECK_EQUAL(early_bits, powLimit.GetCompact());
}

BOOST_AUTO_TEST_SUITE_END()
