// Copyright (c) 2024-2026 QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_EARLYPROTECTION_H
#define BITCOIN_EARLYPROTECTION_H

#include <cstdint>
#include <deque>
#include <map>
#include <mutex>
#include <string>
#include <chrono>

#include <random.h>
#include <uint256.h>

/**
 * QuantumBTC Early Protection System
 * ===================================
 *
 * Active during the first 10,000 blocks or when -earlyprotection=1 flag is set.
 * Protects the young network against hash-rate monopolization and Sybil attacks
 * with three complementary mechanisms:
 *
 * 1. Randomized Activation Delay
 *    New peers start with a random delay (30–300 seconds) before their blocks
 *    are accepted at full weight. Prevents pre-positioned miners from instantly
 *    dominating the chain at launch.
 *
 * 2. Gradual Hashrate Ramp-up
 *    New mining identities begin at 10% block weight. Weight increases linearly
 *    over the next 500 blocks they mine, reaching 100% at block 500.
 *    Formula: weight = 0.10 + 0.90 * min(blocks_mined, 500) / 500
 *
 * 3. Per-IP / Per-Subnet Throttling
 *    No single IP address or /24 subnet can contribute more than 25% of the
 *    most recent 100 blocks. Excess blocks are accepted but at 50% weight
 *    (not rejected), preserving DAG consistency while limiting dominance.
 */

namespace earlyprotection {

/** Maximum height at which protections are active (unless forced on). */
static constexpr int EARLY_PROTECTION_HEIGHT_LIMIT = 10000;

/** Window of recent blocks tracked for per-IP/subnet throttling. */
static constexpr int THROTTLE_WINDOW = 100;

/** Maximum fraction of the window any single IP or /24 may occupy (25%). */
static constexpr double MAX_IP_FRACTION = 0.25;

/** Weight applied to blocks that exceed the per-IP/subnet threshold. */
static constexpr double THROTTLED_WEIGHT = 0.50;

/** Number of blocks a miner must mine before reaching full weight. */
static constexpr int RAMPUP_BLOCKS = 500;

/** Starting weight fraction for a brand-new miner. */
static constexpr double RAMPUP_MIN_WEIGHT = 0.10;

/** Minimum activation delay in seconds for new peers. */
static constexpr int ACTIVATION_DELAY_MIN_SECS = 30;

/** Maximum activation delay in seconds for new peers. */
static constexpr int ACTIVATION_DELAY_MAX_SECS = 300;

/**
 * Extract the /24 subnet prefix from an IP address string.
 * E.g. "192.168.1.42" -> "192.168.1", "::1" -> "::1".
 */
inline std::string GetSubnet24(const std::string& ip)
{
    // For IPv4: strip last octet
    auto pos = ip.rfind('.');
    if (pos != std::string::npos) {
        return ip.substr(0, pos);
    }
    // For IPv6 or other formats: use the full address (conservative)
    return ip;
}

/**
 * EarlyProtectionManager — singleton-style tracker for the three protections.
 *
 * Thread-safe: all public methods acquire m_mutex internally.
 * The manager stores no persistent state; it rebuilds on node restart
 * (appropriate since protections are only for the bootstrap period).
 */
class EarlyProtectionManager
{
public:
    // ---------- Peer Activation Delay ----------

    /**
     * Register a peer and assign a random activation delay.
     * Returns the delay in seconds assigned to this peer.
     */
    int RegisterPeer(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (m_peer_activation.count(peer_id)) {
            return 0; // already registered
        }
        int delay = ACTIVATION_DELAY_MIN_SECS + FastRandomContext{}.randrange(ACTIVATION_DELAY_MAX_SECS - ACTIVATION_DELAY_MIN_SECS + 1);
        auto now = std::chrono::steady_clock::now();
        m_peer_activation[peer_id] = now + std::chrono::seconds(delay);
        return delay;
    }

    /**
     * Check if a peer has completed its activation delay.
     * Returns true if the peer is fully activated (delay elapsed).
     */
    bool IsPeerActivated(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_peer_activation.find(peer_id);
        if (it == m_peer_activation.end()) {
            return false; // unknown peer — not activated
        }
        return std::chrono::steady_clock::now() >= it->second;
    }

    /**
     * Get the weight multiplier for a peer based on activation delay.
     * Returns 1.0 if fully activated, 0.10 if still in delay period.
     */
    double GetActivationWeight(int64_t peer_id)
    {
        if (IsPeerActivated(peer_id)) return 1.0;
        return RAMPUP_MIN_WEIGHT;
    }

    /**
     * Remove a peer from tracking (on disconnect).
     */
    void UnregisterPeer(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_peer_activation.erase(peer_id);
        m_peer_block_count.erase(peer_id);
    }

    // ---------- Gradual Hashrate Ramp-up ----------

    /**
     * Record that a peer mined a block and return the ramp-up weight.
     * Weight = 0.10 + 0.90 * min(blocks_mined, 500) / 500
     */
    double RecordBlockAndGetRampWeight(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        int& count = m_peer_block_count[peer_id];
        count++;
        double frac = std::min(count, RAMPUP_BLOCKS) / static_cast<double>(RAMPUP_BLOCKS);
        return RAMPUP_MIN_WEIGHT + (1.0 - RAMPUP_MIN_WEIGHT) * frac;
    }

    /**
     * Get ramp-up weight for a peer without recording a new block.
     */
    double GetRampWeight(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_peer_block_count.find(peer_id);
        int count = (it != m_peer_block_count.end()) ? it->second : 0;
        double frac = std::min(count, RAMPUP_BLOCKS) / static_cast<double>(RAMPUP_BLOCKS);
        return RAMPUP_MIN_WEIGHT + (1.0 - RAMPUP_MIN_WEIGHT) * frac;
    }

    // ---------- Per-IP / Per-Subnet Throttling ----------

    /**
     * Record a block from a given IP address and return the throttle weight.
     * Returns 1.0 if within limits, THROTTLED_WEIGHT (0.50) if exceeding 25%.
     */
    double RecordBlockIPAndGetThrottleWeight(const std::string& ip)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        std::string subnet = GetSubnet24(ip);

        // Add to sliding window
        m_recent_ips.push_back(ip);
        m_recent_subnets.push_back(subnet);
        if (static_cast<int>(m_recent_ips.size()) > THROTTLE_WINDOW) {
            m_recent_ips.pop_front();
            m_recent_subnets.pop_front();
        }

        // Count this IP and subnet in the window
        int ip_count = 0, subnet_count = 0;
        for (const auto& entry : m_recent_ips) {
            if (entry == ip) ip_count++;
        }
        for (const auto& entry : m_recent_subnets) {
            if (entry == subnet) subnet_count++;
        }

        int window = static_cast<int>(m_recent_ips.size());
        double ip_frac = static_cast<double>(ip_count) / window;
        double subnet_frac = static_cast<double>(subnet_count) / window;

        if (ip_frac > MAX_IP_FRACTION || subnet_frac > MAX_IP_FRACTION) {
            return THROTTLED_WEIGHT;
        }
        return 1.0;
    }

    /**
     * Query current IP/subnet fraction without recording (read-only).
     */
    double GetIPThrottleWeight(const std::string& ip)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        std::string subnet = GetSubnet24(ip);
        int ip_count = 0, subnet_count = 0;
        for (const auto& entry : m_recent_ips) {
            if (entry == ip) ip_count++;
        }
        for (const auto& entry : m_recent_subnets) {
            if (entry == subnet) subnet_count++;
        }
        int window = static_cast<int>(m_recent_ips.size());
        if (window == 0) return 1.0;
        double ip_frac = static_cast<double>(ip_count) / window;
        double subnet_frac = static_cast<double>(subnet_count) / window;
        if (ip_frac > MAX_IP_FRACTION || subnet_frac > MAX_IP_FRACTION) {
            return THROTTLED_WEIGHT;
        }
        return 1.0;
    }

    // ---------- Combined Weight ----------

    /**
     * Compute the combined effective weight for a block from a given peer/IP.
     * The final weight is the product of all three protection multipliers:
     *   effective_weight = activation_weight * ramp_weight * throttle_weight
     *
     * This is applied to nChainWork contribution for the block.
     */
    double ComputeBlockWeight(int64_t peer_id, const std::string& ip)
    {
        double w_activation = GetActivationWeight(peer_id);
        double w_ramp = RecordBlockAndGetRampWeight(peer_id);
        double w_throttle = RecordBlockIPAndGetThrottleWeight(ip);
        return w_activation * w_ramp * w_throttle;
    }

    // ---------- Self-mined blocks (no peer) ----------

    /**
     * For locally-mined blocks, only IP throttling applies.
     * Returns the throttle weight for the local node's IP (127.0.0.1).
     */
    double RecordLocalBlock()
    {
        return RecordBlockIPAndGetThrottleWeight("127.0.0.1");
    }

    /**
     * Get the block count attributed to a peer (for ramp-up display).
     */
    int GetPeerBlockCount(int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_peer_block_count.find(peer_id);
        return (it != m_peer_block_count.end()) ? it->second : 0;
    }

    // ---------- Per-block weight pre-computation ----------

    /**
     * Called by net_processing before ProcessBlock to pre-compute the early
     * protection weight for a block received from a peer.
     * AcceptBlock (in validation.cpp) later retrieves this via PopBlockWeight.
     */
    void SetBlockWeight(const uint256& block_hash, double weight,
                        const std::string& ip, int64_t peer_id)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_pending_block_weights[block_hash] = {weight, ip, peer_id};
    }

    struct BlockWeightInfo {
        double weight{1.0};
        std::string ip;
        int64_t peer_id{-1};
    };

    /**
     * Pop the pre-computed weight for a block (called by AcceptBlock).
     * Returns the weight info if found, or {1.0, "127.0.0.1", -1} if not
     * (e.g. locally-mined block).
     */
    BlockWeightInfo PopBlockWeight(const uint256& block_hash)
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        auto it = m_pending_block_weights.find(block_hash);
        if (it != m_pending_block_weights.end()) {
            BlockWeightInfo info = it->second;
            m_pending_block_weights.erase(it);
            return info;
        }
        return {1.0, "127.0.0.1", -1};
    }

    /**
     * Reset all tracking state (for testing).
     */
    void Reset()
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_peer_activation.clear();
        m_peer_block_count.clear();
        m_recent_ips.clear();
        m_recent_subnets.clear();
    }

private:
    std::mutex m_mutex;

    /** Peer ID -> activation time point (after which full weight applies). */
    std::map<int64_t, std::chrono::steady_clock::time_point> m_peer_activation;

    /** Peer ID -> number of blocks mined (for ramp-up). */
    std::map<int64_t, int> m_peer_block_count;

    /** Sliding window of recent block source IPs. */
    std::deque<std::string> m_recent_ips;

    /** Sliding window of recent block source /24 subnets. */
    std::deque<std::string> m_recent_subnets;

    /** Pre-computed block weights set by net_processing, consumed by AcceptBlock. */
    std::map<uint256, BlockWeightInfo> m_pending_block_weights;
};

} // namespace earlyprotection

#endif // BITCOIN_EARLYPROTECTION_H
