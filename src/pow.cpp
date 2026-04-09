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

/**
 * GetNextWorkRequired for QuantumBTC BlockDAG mode.
 *
 * When DAG mode is enabled (params.fDagMode), we use a per-window DAA
 * (Difficulty Adjustment Algorithm) similar to Kaspa's:
 *   - Target: nDagTargetSpacingMs (default 1000 ms / 1 second)
 *   - Window: params.nDagDiffWindowSize blocks (default 4032; testnet 128)
 *   - Adjustment: clamp ratio to [1/4, 4] per window
 *
 * The PoW algorithm remains SHA-256 (ASIC/GPU compatible).
 */
unsigned int GetNextWorkRequiredDAG(const CBlockIndex* pindexLast, const CBlockHeader* pblock, const Consensus::Params& params)
{
    assert(pindexLast != nullptr);
    const unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();

    if (params.fPowNoRetargeting) {
        return pindexLast->nBits;
    }

    const int64_t nWindow = params.nDagDiffWindowSize;

    // Allow any difficulty in early blocks (first adjustment window)
    if (pindexLast->nHeight < nWindow) {
        return nProofOfWorkLimit;
    }

    const int64_t nTargetSpacing = params.nDagTargetSpacingMs / 1000;
    if (nTargetSpacing <= 0) return pindexLast->nBits;

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

    const arith_uint256 bnPowLimit = UintToArith256(params.powLimit);
    arith_uint256 bnNew;
    bnNew.SetCompact(pindexLast->nBits);
    bnNew *= nActualTimespan;
    bnNew /= nTargetTimespan;

    // Transaction-load-aware difficulty adjustment.
    //
    // After the time-based retarget, scale the target down (harder PoW)
    // proportionally to how busy the network has been over the same window.
    // This makes a 51% attack most expensive exactly when the network carries
    // the most economic value, while keeping difficulty low during quiet periods
    // so that household miners stay competitive.
    //
    // Multiplier formula (linear ramp, integer arithmetic):
    //   avg_tx      = transactions per block over the 4031-block window
    //   excess      = clamp(avg_tx − baseline, 0, (max_mult−1) × baseline)
    //   load_num    = baseline + excess          ∈ [baseline, max_mult×baseline]
    //   new_target  = time_target × baseline / load_num
    //                 (smaller target = higher difficulty)
    if (params.nLoadDiffBaseline > 0 && params.nLoadDiffMaxMultiplier > 1) {
        const uint64_t tx_last  = pindexLast->m_chain_tx_count;
        const uint64_t tx_first = pindexFirst->m_chain_tx_count;
        if (tx_last > tx_first) {
            const int64_t kWindow = nWindow - 1;
            // Divide in uint64_t first, then cast — result fits in int64_t since
            // even at uint64_t max the quotient is only ~4.5×10^15 < INT64_MAX.
            const int64_t avg_tx  = static_cast<int64_t>((tx_last - tx_first) / static_cast<uint64_t>(kWindow));
            const int64_t baseline  = params.nLoadDiffBaseline;
            const int64_t max_mult  = params.nLoadDiffMaxMultiplier;

            if (avg_tx > baseline) {
                const int64_t max_excess = (max_mult - 1) * baseline;
                const int64_t excess     = std::min(avg_tx - baseline, max_excess);
                const int64_t load_num   = baseline + excess;

                // Reduce target proportionally (load_num > baseline ⟹ target shrinks)
                bnNew = bnNew * arith_uint256(static_cast<uint64_t>(baseline))
                             / arith_uint256(static_cast<uint64_t>(load_num));
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
