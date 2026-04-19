// Copyright (c) 2026 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NODE_SV2_TRANSPORT_H
#define BITCOIN_NODE_SV2_TRANSPORT_H

#include <sync.h>

#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <unordered_map>
#include <vector>

template <typename C> class Span;

namespace interfaces {
class Handler;
class Mining;
struct NewTemplate;
struct SetNewPrevHash;
} // namespace interfaces

namespace node {

enum class SV2MessageType : uint8_t {
    NEW_TEMPLATE = 1,
    SET_NEW_PREV_HASH = 2,
    SUBMIT_SOLUTION = 3,
};

struct SV2TransportStats {
    bool running{false};
    size_t connected_clients{0};
    uint64_t next_sequence{1};
    size_t queued_outbound_frames{0};
    size_t queued_submit_frames{0};
};

/**
 * SV2 transport skeleton:
 * - Tracks persistent client sessions
 * - Implements length-prefixed binary frame parsing entrypoint
 * - Broadcasts NewTemplate/SetNewPrevHash notifications as framed messages
 */
class SV2Transport
{
public:
    explicit SV2Transport(interfaces::Mining& mining);
    ~SV2Transport();

    bool Start() EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    void Stop() EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    bool IsRunning() const EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);

    void OnClientConnected(uint64_t client_id) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    void OnClientDisconnected(uint64_t client_id) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    void OnClientBytes(uint64_t client_id, Span<const uint8_t> bytes) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);

    std::vector<std::vector<uint8_t>> DrainOutboundFrames(uint64_t client_id) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    std::vector<std::vector<uint8_t>> DrainSubmitFrames(uint64_t client_id) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    SV2TransportStats GetStats() const EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);

private:
    struct ClientState {
        std::vector<uint8_t> rx_buffer;
        std::deque<std::vector<uint8_t>> outbound_frames;
        std::deque<std::vector<uint8_t>> submit_frames;
    };

    interfaces::Mining& m_mining;
    mutable Mutex m_mutex;
    bool m_running GUARDED_BY(m_mutex){false};
    uint64_t m_next_sequence GUARDED_BY(m_mutex){1};
    std::unordered_map<uint64_t, ClientState> m_clients GUARDED_BY(m_mutex);
    std::unique_ptr<interfaces::Handler> m_new_template_handler GUARDED_BY(m_mutex);
    std::unique_ptr<interfaces::Handler> m_set_new_prev_hash_handler GUARDED_BY(m_mutex);

    static constexpr size_t MAX_FRAME_SIZE{4 * 1024 * 1024};

    void OnNewTemplate(const interfaces::NewTemplate& update) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    void OnSetNewPrevHash(const interfaces::SetNewPrevHash& update) EXCLUSIVE_LOCKS_REQUIRED(!m_mutex);
    void ParseClientFrames(uint64_t client_id) EXCLUSIVE_LOCKS_REQUIRED(m_mutex);
    void HandleInboundFrame(ClientState& client, Span<const uint8_t> frame) EXCLUSIVE_LOCKS_REQUIRED(m_mutex);
    void BroadcastFrame(SV2MessageType type, const std::vector<uint8_t>& payload) EXCLUSIVE_LOCKS_REQUIRED(m_mutex);
    static std::vector<uint8_t> EncodeFrame(SV2MessageType type, uint64_t sequence, const std::vector<uint8_t>& payload);
};

} // namespace node

#endif // BITCOIN_NODE_SV2_TRANSPORT_H
