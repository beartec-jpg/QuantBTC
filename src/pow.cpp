// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2022 The Bitcoin Core developers
// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <pow.h>

#include <algorithm>
#include <arith_uint256.h>
#include <chain.h>
#include <common/args.h>
#include <primitives/block.h>
#include <uint256.h>

namespace {

uint64_t IntegerSquareRoot(uint64_t n)
{
    uint64_t bit = uint64_t{1} << 62;
    uint64_t result = 0;

    while (bit > n) bit >>= 2;

    while (bit != 0) {
        if (n >= result + bit) {
            n -= result + bit;
            result = (result >> 1) + bit;
        } else {
            result >>= 1;
        }
        bit >>= 2;
    }

    return result;
}

} // namespace

/**
 * GetNextWorkRequired for QuantumBTC BlockDAG mode.
 *
 * Two modes:
 *
 * 1. Legacy fixed-window (fDagUseEma == false):
 *    Retargets every nDagDiffWindowSize blocks using actual/target timespan.
 *
 * 2. Dual-EMA per-block (fDagUseEma == true):
 *    Adjusts difficulty EVERY block using two Exponential Moving Averages
 *    of block times:
 *      - Fast EMA (short half-life): reacts quickly to block-rate spikes
 *      - Slow EMA (long half-life):  provides stability / dampening
 *    Effective block-time estimate = 0.7 * fast_ema + 0.3 * slow_ema
 *    Difficulty adjusts by (effective_estimate / target), clamped per-block.
 *
 * Both modes keep the transaction-load-aware sqrt multiplier on top.
 */

namespace {

/**
 * Compute an exponential moving average of block times by walking the
 * ancestor chain.  halfLife is in blocks.  Returns the EMA in seconds
 * (fixed-point with 16-bit fraction, i.e. scaled by 65536).
 *
 * alpha = 1 - 0.5^(1/halfLife)  ≈  0.693 / halfLife  for small alpha
 * We use fixed-point arithmetic (FP_SCALE = 1<<16) throughout.
 */
uint64_t ComputeBlockTimeEMA(const CBlockIndex* pindexLast, int64_t halfLife, int64_t maxLookback)
{
    // alpha_fp = alpha * FP_SCALE.  alpha = 1 - exp(-ln2/halfLife).
    // For integer math: alpha ≈ 45426 / halfLife  (= 0.693 * 65536 / halfLife)
    constexpr uint64_t FP_SCALE = 1ULL << 16;
    const uint64_t alpha_fp = std::max<uint64_t>(1ULL, 45426ULL / static_cast<uint64_t>(std::max<int64_t>(1, halfLife)));
    const uint64_t one_minus_alpha = FP_SCALE - alpha_fp;

    // Walk backwards, accumulating weighted block times.
    // EMA_n = alpha * sample_n + (1-alpha) * EMA_{n-1}
    // We seed the EMA with the oldest sample we look at.
    const CBlockIndex* cur = pindexLast;
    int64_t limit = std::min(maxLookback, static_cast<int64_t>(pindexLast->nHeight));

    // Collect block times in reverse (newest first)
    std::vector<int64_t> block_times;
    block_times.reserve(limit);
    for (int64_t i = 0; i < limit && cur && cur->pprev; ++i) {
        int64_t bt = cur->GetBlockTime() - cur->pprev->GetBlockTime();
        if (bt < 1) bt = 1;
        block_times.push_back(bt);
        cur = cur->pprev;
    }

    if (block_times.empty()) {
        // No history — return target as default
        return 10 * FP_SCALE; // fallback
    }

    // Process oldest-first to build the EMA correctly
    uint64_t ema_fp = static_cast<uint64_t>(block_times.back()) * FP_SCALE;
    for (int64_t i = static_cast<int64_t>(block_times.size()) - 1; i >= 0; --i) {
        uint64_t sample_fp = static_cast<uint64_t>(block_times[i]) * FP_SCALE;
        ema_fp = (alpha_fp * sample_fp + one_minus_alpha * ema_fp) / FP_SCALE;
    }

    return ema_fp;
}

} // anon namespace

unsigned int GetNextWorkRequiredDAG(const CBlockIndex* pindexLast, const CBlockHeader* pblock, const Consensus::Params& params)
{
    assert(pindexLast != nullptr);
    const unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();

    if (params.fPowNoRetargeting) {
        return pindexLast->nBits;
    }

    const int64_t nTargetSpacing = params.nDagTargetSpacingMs / 1000;
    if (nTargetSpacing <= 0) return pindexLast->nBits;

    const arith_uint256 bnPowLimit = UintToArith256(params.powLimit);

    // ── Dual-EMA per-block DAA ──────────────────────────────────────────
    if (params.fDagUseEma) {
        // Grace period: use minimum difficulty for the first nDagDiffWindowSize
        // blocks so the chain can bootstrap.  The EMA only considers blocks
        // mined *after* this activation height, preventing fast bootstrap
        // blocks from inflating difficulty.
        const int emaActivation = std::max(4, static_cast<int>(params.nDagDiffWindowSize));
        if (pindexLast->nHeight < emaActivation) {
            return nProofOfWorkLimit;
        }

        // Allow min-difficulty blocks on testnet when blocks are very slow
        if (params.fPowAllowMinDifficultyBlocks) {
            if (pblock->GetBlockTime() > pindexLast->GetBlockTime() + nTargetSpacing * 4) {
                return nProofOfWorkLimit;
            }
        }

        constexpr uint64_t FP_SCALE = 1ULL << 16;
        // Only look at post-activation blocks so bootstrap fast-mining is ignored
        const int64_t postActivation = static_cast<int64_t>(pindexLast->nHeight) - emaActivation;
        const int64_t effectiveLookback = std::min(static_cast<int64_t>(params.nDagDiffWindowSize), postActivation);

        // Compute both EMAs
        uint64_t fast_ema_fp = ComputeBlockTimeEMA(pindexLast, params.nDagEmaFastHalfLife, effectiveLookback);
        uint64_t slow_ema_fp = ComputeBlockTimeEMA(pindexLast, params.nDagEmaSlowHalfLife, effectiveLookback);

        // Blend: 70% fast + 30% slow — fast dominates for responsiveness,
        // slow prevents whiplash.
        uint64_t blended_fp = (fast_ema_fp * 7 + slow_ema_fp * 3) / 10;
        uint64_t target_fp  = static_cast<uint64_t>(nTargetSpacing) * FP_SCALE;

        // Avoid division by zero
        if (blended_fp == 0) blended_fp = 1;
        if (target_fp == 0)  target_fp  = FP_SCALE;

        // adjustment = blended_ema / target.  >1 means blocks are slow (ease up),
        // <1 means blocks are fast (tighten).
        // We compute (blended * 1000) / target to get millionths precision.
        uint64_t adjust_milli = (blended_fp * 1000) / target_fp;

        // Clamp per-block adjustment
        const uint64_t maxAdj = static_cast<uint64_t>(params.nDagEmaMaxAdjust); // e.g. 3000 = 3×
        const uint64_t minAdj = 1000000 / maxAdj; // inverse, e.g. 333 = 1/3×
        if (adjust_milli > maxAdj) adjust_milli = maxAdj;
        if (adjust_milli < minAdj) adjust_milli = minAdj;

        // new_target = old_target * adjustment
        // Higher target = easier mining.  When blocks are fast, adjustment < 1000
        // → target shrinks → difficulty rises.
        // Divide first to avoid 256-bit overflow with very large targets.
        arith_uint256 bnNew;
        bnNew.SetCompact(pindexLast->nBits);
        bnNew = (bnNew / arith_uint256(1000)) * arith_uint256(adjust_milli);

        // Transaction-load-aware multiplier (per-block version)
        if (params.nLoadDiffBaseline > 0 && params.nLoadDiffMaxMultiplier > 1 && pindexLast->pprev) {
            // Use a rolling window of recent post-activation blocks for avg tx count
            const int64_t loadWindow = std::min<int64_t>(params.nDagEmaSlowHalfLife * 2, postActivation);
            const CBlockIndex* pOlder = pindexLast->GetAncestor(pindexLast->nHeight - static_cast<int>(loadWindow));
            if (pOlder && pindexLast->m_chain_tx_count > pOlder->m_chain_tx_count) {
                const int64_t avg_tx = static_cast<int64_t>((pindexLast->m_chain_tx_count - pOlder->m_chain_tx_count) / static_cast<uint64_t>(loadWindow));
                const uint64_t baseline = static_cast<uint64_t>(params.nLoadDiffBaseline);
                const uint64_t max_mult = static_cast<uint64_t>(params.nLoadDiffMaxMultiplier);

                if (avg_tx > 0 && static_cast<uint64_t>(avg_tx) > baseline) {
                    const uint64_t capped_avg_tx = std::min<uint64_t>(
                        static_cast<uint64_t>(avg_tx),
                        baseline * max_mult * max_mult);
                    const uint64_t ratio_scaled = (capped_avg_tx * FP_SCALE * FP_SCALE) / baseline;
                    uint64_t load_mult_scaled = IntegerSquareRoot(ratio_scaled);

                    if (load_mult_scaled < FP_SCALE) load_mult_scaled = FP_SCALE;
                    if (load_mult_scaled > max_mult * FP_SCALE) load_mult_scaled = max_mult * FP_SCALE;

                    bnNew = bnNew * arith_uint256(FP_SCALE) / arith_uint256(load_mult_scaled);
                }
            }
        }

        if (bnNew > bnPowLimit) bnNew = bnPowLimit;
        return bnNew.GetCompact();
    }

    // ── Legacy fixed-window DAA ─────────────────────────────────────────
    const int64_t nWindow = params.nDagDiffWindowSize;

    // Allow any difficulty in early blocks (first adjustment window)
    if (pindexLast->nHeight < nWindow) {
        return nProofOfWorkLimit;
    }

    const int64_t nTargetTimespan = nWindow * nTargetSpacing;

    // Retarget every nWindow blocks
    if ((pindexLast->nHeight + 1) % nWindow != 0) {
        // Allow min-difficulty blocks on testnet
        if (params.fPowAllowMinDifficultyBlocks) {
            if (pblock->GetBlockTime() > pindexLast->GetBlockTime() + nTargetSpacing * 2) {
                return nProofOfWorkLimit;
            }
        }
        return pindexLast->nBits;
    }

    const CBlockIndex* pindexFirst = pindexLast->GetAncestor(pindexLast->nHeight - (nWindow - 1));
    assert(pindexFirst);

    int64_t nActualTimespan = pindexLast->GetBlockTime() - pindexFirst->GetBlockTime();
    // Clamp adjustment
    if (nActualTimespan < nTargetTimespan / 4) nActualTimespan = nTargetTimespan / 4;
    if (nActualTimespan > nTargetTimespan * 4) nActualTimespan = nTargetTimespan * 4;

    arith_uint256 bnNew;
    bnNew.SetCompact(pindexLast->nBits);
    bnNew *= nActualTimespan;
    bnNew /= nTargetTimespan;

    // Transaction-load-aware difficulty adjustment.
    //
    // Version 2 uses a gentler square-root ramp instead of the old linear one:
    //   avg_tx       = transactions per block over the 4031-block window
    //   load_ratio   = avg_tx / baseline
    //   load_mult    = clamp(sqrt(load_ratio), 1, max_mult)
    //   new_target   = time_target / load_mult
    //
    // This still raises attack cost during sustained congestion, but avoids
    // overreacting to moderate bursts in normal network activity.
    if (params.nLoadDiffBaseline > 0 && params.nLoadDiffMaxMultiplier > 1) {
        const uint64_t tx_last  = pindexLast->m_chain_tx_count;
        const uint64_t tx_first = pindexFirst->m_chain_tx_count;
        if (tx_last > tx_first) {
            const int64_t kWindow = nWindow - 1;
            const int64_t avg_tx = static_cast<int64_t>((tx_last - tx_first) / static_cast<uint64_t>(kWindow));
            const uint64_t baseline = static_cast<uint64_t>(params.nLoadDiffBaseline);
            const uint64_t max_mult = static_cast<uint64_t>(params.nLoadDiffMaxMultiplier);

            if (avg_tx > 0 && static_cast<uint64_t>(avg_tx) > baseline) {
                constexpr uint64_t FP_SCALE = 1U << 16;
                const uint64_t capped_avg_tx = std::min<uint64_t>(
                    static_cast<uint64_t>(avg_tx),
                    baseline * max_mult * max_mult);
                const uint64_t ratio_scaled = (capped_avg_tx * FP_SCALE * FP_SCALE) / baseline;
                uint64_t load_mult_scaled = IntegerSquareRoot(ratio_scaled);

                if (load_mult_scaled < FP_SCALE) load_mult_scaled = FP_SCALE;
                if (load_mult_scaled > max_mult * FP_SCALE) load_mult_scaled = max_mult * FP_SCALE;

                bnNew = bnNew * arith_uint256(FP_SCALE) / arith_uint256(load_mult_scaled);
            }
        }
    }

    if (bnNew > bnPowLimit) bnNew = bnPowLimit;

    return bnNew.GetCompact();
}

unsigned int GetNextWorkRequired(const CBlockIndex* pindexLast, const CBlockHeader *pblock, const Consensus::Params& params)
{
    assert(pindexLast != nullptr);
    unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();

    // QuantumBTC: use DAG-specific difficulty adjustment when in DAG mode
    if (gArgs.GetBoolArg("-dag", params.fDagMode)) {
        return GetNextWorkRequiredDAG(pindexLast, pblock, params);
    }

    // Only change once per difficulty adjustment interval
    if ((pindexLast->nHeight+1) % params.DifficultyAdjustmentInterval() != 0)
    {
        if (params.fPowAllowMinDifficultyBlocks)
        {
            // Special difficulty rule for testnet:
            // If the new block's timestamp is more than 2* 10 minutes
            // then allow mining of a min-difficulty block.
            if (pblock->GetBlockTime() > pindexLast->GetBlockTime() + params.nPowTargetSpacing*2)
                return nProofOfWorkLimit;
            else
            {
                // Return the last non-special-min-difficulty-rules-block
                const CBlockIndex* pindex = pindexLast;
                while (pindex->pprev && pindex->nHeight % params.DifficultyAdjustmentInterval() != 0 && pindex->nBits == nProofOfWorkLimit)
                    pindex = pindex->pprev;
                return pindex->nBits;
            }
        }
        return pindexLast->nBits;
    }

    // Go back by what we want to be 14 days worth of blocks
    int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
    assert(nHeightFirst >= 0);
    const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
    assert(pindexFirst);

    return CalculateNextWorkRequired(pindexLast, pindexFirst->GetBlockTime(), params);
}

unsigned int CalculateNextWorkRequired(const CBlockIndex* pindexLast, int64_t nFirstBlockTime, const Consensus::Params& params)
{
    if (params.fPowNoRetargeting)
        return pindexLast->nBits;

    // Limit adjustment step
    int64_t nActualTimespan = pindexLast->GetBlockTime() - nFirstBlockTime;
    if (nActualTimespan < params.nPowTargetTimespan/4)
        nActualTimespan = params.nPowTargetTimespan/4;
    if (nActualTimespan > params.nPowTargetTimespan*4)
        nActualTimespan = params.nPowTargetTimespan*4;

    // Retarget
    const arith_uint256 bnPowLimit = UintToArith256(params.powLimit);
    arith_uint256 bnNew;

    // Special difficulty rule for Testnet4
    if (params.enforce_BIP94) {
        // Here we use the first block of the difficulty period. This way
        // the real difficulty is always preserved in the first block as
        // it is not allowed to use the min-difficulty exception.
        int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
        const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
        bnNew.SetCompact(pindexFirst->nBits);
    } else {
        bnNew.SetCompact(pindexLast->nBits);
    }

    bnNew *= nActualTimespan;
    bnNew /= params.nPowTargetTimespan;

    if (bnNew > bnPowLimit)
        bnNew = bnPowLimit;

    return bnNew.GetCompact();
}

// Check that on difficulty adjustments, the new difficulty does not increase
// or decrease beyond the permitted limits.
bool PermittedDifficultyTransition(const Consensus::Params& params, int64_t height, uint32_t old_nbits, uint32_t new_nbits)
{
    if (params.fPowAllowMinDifficultyBlocks) return true;

    if (height % params.DifficultyAdjustmentInterval() == 0) {
        int64_t smallest_timespan = params.nPowTargetTimespan/4;
        int64_t largest_timespan = params.nPowTargetTimespan*4;

        const arith_uint256 pow_limit = UintToArith256(params.powLimit);
        arith_uint256 observed_new_target;
        observed_new_target.SetCompact(new_nbits);

        // Calculate the largest difficulty value possible:
        arith_uint256 largest_difficulty_target;
        largest_difficulty_target.SetCompact(old_nbits);
        largest_difficulty_target *= largest_timespan;
        largest_difficulty_target /= params.nPowTargetTimespan;

        if (largest_difficulty_target > pow_limit) {
            largest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 maximum_new_target;
        maximum_new_target.SetCompact(largest_difficulty_target.GetCompact());
        if (maximum_new_target < observed_new_target) return false;

        // Calculate the smallest difficulty value possible:
        arith_uint256 smallest_difficulty_target;
        smallest_difficulty_target.SetCompact(old_nbits);
        smallest_difficulty_target *= smallest_timespan;
        smallest_difficulty_target /= params.nPowTargetTimespan;

        if (smallest_difficulty_target > pow_limit) {
            smallest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 minimum_new_target;
        minimum_new_target.SetCompact(smallest_difficulty_target.GetCompact());
        if (minimum_new_target > observed_new_target) return false;
    } else if (old_nbits != new_nbits) {
        return false;
    }
    return true;
}

bool CheckProofOfWork(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    bool fNegative;
    bool fOverflow;
    arith_uint256 bnTarget;

    bnTarget.SetCompact(nBits, &fNegative, &fOverflow);

    // Check range
    if (fNegative || bnTarget == 0 || fOverflow || bnTarget > UintToArith256(params.powLimit))
        return false;

    // Check proof of work matches claimed amount
    if (UintToArith256(hash) > bnTarget)
        return false;

    return true;
}
