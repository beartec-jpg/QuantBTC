// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2022 The Bitcoin Core developers
// Upstream/inherited portions of this file remain under the MIT software license.
// BearTec-authored modifications added on or after 2026-03-09 are separately
// claimed under the Business Source License 1.1 until 2030-04-09, to the extent
// those deltas are separable and identifiable. See LICENSE-BUSL and NOTICE.

#ifndef BITCOIN_CONSENSUS_PARAMS_H
#define BITCOIN_CONSENSUS_PARAMS_H

#include <uint256.h>

#include <chrono>
#include <limits>
#include <map>
#include <vector>

namespace Consensus {

/**
 * A buried deployment is one where the height of the activation has been hardcoded into
 * the client implementation long after the consensus change has activated. See BIP 90.
 */
enum BuriedDeployment : int16_t {
    // buried deployments get negative values to avoid overlap with DeploymentPos
    DEPLOYMENT_HEIGHTINCB = std::numeric_limits<int16_t>::min(),
    DEPLOYMENT_CLTV,
    DEPLOYMENT_DERSIG,
    DEPLOYMENT_CSV,
    DEPLOYMENT_SEGWIT,
};
constexpr bool ValidDeployment(BuriedDeployment dep) { return dep <= DEPLOYMENT_SEGWIT; }

enum DeploymentPos : uint16_t {
    DEPLOYMENT_TESTDUMMY,
    DEPLOYMENT_TAPROOT, // Deployment of Schnorr/Taproot (BIPs 340-342)
    DEPLOYMENT_PQC,     // Deployment of post-quantum cryptography (ML-DSA / SLH-DSA)
    // NOTE: Also add new deployments to VersionBitsDeploymentInfo in deploymentinfo.cpp
    MAX_VERSION_BITS_DEPLOYMENTS
};
constexpr bool ValidDeployment(DeploymentPos dep) { return dep < MAX_VERSION_BITS_DEPLOYMENTS; }

/**
 * Struct for each individual consensus rule change using BIP9.
 */
struct BIP9Deployment {
    /** Bit position to select the particular bit in nVersion. */
    int bit{28};
    /** Start MedianTime for version bits miner confirmation. Can be a date in the past */
    int64_t nStartTime{NEVER_ACTIVE};
    /** Timeout/expiry MedianTime for the deployment attempt. */
    int64_t nTimeout{NEVER_ACTIVE};
    /** If lock in occurs, delay activation until at least this block
     *  height.  Note that activation will only occur on a retarget
     *  boundary.
     */
    int min_activation_height{0};

    /** Constant for nTimeout very far in the future. */
    static constexpr int64_t NO_TIMEOUT = std::numeric_limits<int64_t>::max();

    /** Special value for nStartTime indicating that the deployment is always active.
     *  This is useful for testing, as it means tests don't need to deal with the activation
     *  process (which takes at least 3 BIP9 intervals). Only tests that specifically test the
     *  behaviour during activation cannot use this. */
    static constexpr int64_t ALWAYS_ACTIVE = -1;

    /** Special value for nStartTime indicating that the deployment is never active.
     *  This is useful for integrating the code changes for a new feature
     *  prior to deploying it on some or all networks. */
    static constexpr int64_t NEVER_ACTIVE = -2;
};

/**
 * Parameters that influence chain consensus.
 */
struct Params {
    uint256 hashGenesisBlock;
    int nSubsidyHalvingInterval;
    /**
     * Hashes of blocks that
     * - are known to be consensus valid, and
     * - buried in the chain, and
     * - fail if the default script verify flags are applied.
     */
    std::map<uint256, uint32_t> script_flag_exceptions;
    /** Block height and hash at which BIP34 becomes active */
    int BIP34Height;
    uint256 BIP34Hash;
    /** Block height at which BIP65 becomes active */
    int BIP65Height;
    /** Block height at which BIP66 becomes active */
    int BIP66Height;
    /** Block height at which CSV (BIP68, BIP112 and BIP113) becomes active */
    int CSVHeight;
    /** Block height at which Segwit (BIP141, BIP143 and BIP147) becomes active.
     * Note that segwit v0 script rules are enforced on all blocks except the
     * BIP 16 exception blocks. */
    int SegwitHeight;
    /** Don't warn about unknown BIP 9 activations below this height.
     * This prevents us from warning about the CSV and segwit activations. */
    int MinBIP9WarningHeight;
    /**
     * Minimum blocks including miner confirmation of the total of 2016 blocks in a retargeting period,
     * (nPowTargetTimespan / nPowTargetSpacing) which is also used for BIP9 deployments.
     * Examples: 1916 for 95%, 1512 for testchains.
     */
    uint32_t nRuleChangeActivationThreshold;
    uint32_t nMinerConfirmationWindow;
    BIP9Deployment vDeployments[MAX_VERSION_BITS_DEPLOYMENTS];
    /** Proof of work parameters */
    uint256 powLimit;
    bool fPowAllowMinDifficultyBlocks;
    /**
      * Enfore BIP94 timewarp attack mitigation. On testnet4 this also enforces
      * the block storm mitigation.
      */
    bool enforce_BIP94;
    bool fPowNoRetargeting;
    int64_t nPowTargetSpacing;
    int64_t nPowTargetTimespan;
    std::chrono::seconds PowTargetSpacing() const
    {
        return std::chrono::seconds{nPowTargetSpacing};
    }
    int64_t DifficultyAdjustmentInterval() const { return nPowTargetTimespan / nPowTargetSpacing; }
    /** The best chain should have at least this much work */
    uint256 nMinimumChainWork;
    /** By default assume that the signatures in ancestors of this block are valid */
    uint256 defaultAssumeValid;

    // -------------------------------------------------------------------------
    // QuantumBTC BlockDAG (GHOSTDAG) consensus parameters
    // -------------------------------------------------------------------------

    /**
     * Enable BlockDAG mode. When true, blocks may reference multiple parents
     * and GHOSTDAG consensus is used to determine the canonical ordering.
     */
    bool fDagMode{false};

    /**
     * GHOSTDAG K parameter: maximum anti-cone size for a block to be
     * classified as "blue". Higher K tolerates more concurrent blocks
     * (higher TPS) at the cost of weaker security assumptions.
     * Kaspa uses K=18; QuantumBTC defaults to 32 for broader inclusivity.
     *
     * ── People's Chain Design Rationale ──────────────────────────────────────
     * Higher K = more concurrent blocks treated as "blue" = more miners
     * earning block rewards per epoch.  Combined with fast (~1 s) DAG blocks,
     * small miners find blocks frequently and are NOT orphaned: both a home
     * miner's block and a pool's block can both be blue in the same DAG
     * window.  SHA-256 is retained for merge-mining compatibility with
     * Bitcoin (miners point existing hardware at QBTC at zero extra cost).
     * The DAG is the equalizer — not the hash algorithm.
     * ─────────────────────────────────────────────────────────────────────────
     */
    uint32_t ghostdag_k{32};

    /**
     * Target block interval in milliseconds for the BlockDAG.
     * QuantumBTC targets ~1 second intervals (1000 ms).
     * Used when fDagMode=true instead of nPowTargetSpacing.
     */
    int64_t nDagTargetSpacingMs{1000};

    /**
     * DAG difficulty adjustment window size (in blocks).
     * Retarget occurs every nDagDiffWindowSize blocks.
     * Default 4032 (~67 min at 1 s/block); shorter values give faster convergence.
     */
    int64_t nDagDiffWindowSize{4032};

    /**
     * Maximum number of parent references a DAG block may include.
     * Increased to 64 to match the higher ghostdag_k and provide better
     * DAG connectivity for a widely distributed miner set.
     * (Matches dag::MAX_BLOCK_PARENTS)
     */
    uint32_t nMaxDagParents{64};

    /**
     * Increase maximum block weight to accommodate larger PQC signatures
     * (Dilithium/SPHINCS+/Falcon are 1–50× larger than ECDSA).
     * Default: 4× Bitcoin's MAX_BLOCK_WEIGHT.
     */
    uint32_t nMaxBlockWeightPQC{4 * 4000000};

    /**
     * Block height at which SCRIPT_VERIFY_HYBRID_SIG becomes enforced, requiring
     * all P2WPKH inputs to carry a PQC (4-element) witness rather than an
     * ECDSA-only (2-element) witness.
     *
     * This gives users a migration window after DEPLOYMENT_PQC activates: wallets
     * can continue sending ECDSA-only transactions until this height is reached,
     * after which only hybrid (ECDSA + PQC) witnesses are accepted.
     *
     * std::numeric_limits<int>::max() means "not yet scheduled" (effectively
     * disabled).  Each chain class sets its own height below.
     */
    int nHybridSigHeight{std::numeric_limits<int>::max()};

    // -------------------------------------------------------------------------
    // QuantumBTC Transaction-Load-Aware Difficulty (DAG mode only)
    // -------------------------------------------------------------------------

    /**
     * Average transactions per block above which the load-based difficulty
     * multiplier activates.  At exactly this rate the multiplier is 1× (no
     * change).  It grows linearly up to nLoadDiffMaxMultiplier× as the
     * average rate reaches nLoadDiffMaxMultiplier * nLoadDiffBaseline tx/block.
     *
     * Rationale: raises the PoW attack cost proportionally to economic
     * activity — the network is hardest to attack precisely when it carries
     * the most value.  During quiet periods the baseline stays low so that
     * household miners remain competitive.
     *
     * 0 = feature disabled (default for chains that do not set this).
     */
    int64_t nLoadDiffBaseline{0};

    /**
     * Maximum load-based difficulty multiplier (cap).
     * E.g., 4 means difficulty can be at most 4× harder than the pure
     * time-based retarget result when the network is at sustained peak load.
     * Must be ≥ 1; values < 2 effectively disable the feature.
     */
    int64_t nLoadDiffMaxMultiplier{4};

    // -------------------------------------------------------------------------
    // QuantumBTC Early Protection (anti-monopolization for bootstrap period)
    // -------------------------------------------------------------------------

    /**
     * Enable early-chain protections: randomized activation delay, gradual
     * hash-rate ramp-up, and per-IP/subnet throttling.  Active during the
     * first 10,000 blocks OR whenever forced on by the -earlyprotection flag.
     *
     * Default: true for regtest/testnet, false for mainnet.
     */
    bool fEarlyProtection{false};

    /**
     * If true, witness commitments contain a payload equal to a Bitcoin Script solution
     * to the signet challenge. See BIP325.
     */
    bool signet_blocks{false};
    std::vector<uint8_t> signet_challenge;

    int DeploymentHeight(BuriedDeployment dep) const
    {
        switch (dep) {
        case DEPLOYMENT_HEIGHTINCB:
            return BIP34Height;
        case DEPLOYMENT_CLTV:
            return BIP65Height;
        case DEPLOYMENT_DERSIG:
            return BIP66Height;
        case DEPLOYMENT_CSV:
            return CSVHeight;
        case DEPLOYMENT_SEGWIT:
            return SegwitHeight;
        } // no default case, so the compiler can warn about missing cases
        return std::numeric_limits<int>::max();
    }
};

} // namespace Consensus

#endif // BITCOIN_CONSENSUS_PARAMS_H
