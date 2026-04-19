// Copyright (c) 2026 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <interfaces/handler.h>
#include <interfaces/mining.h>
#include <logging.h>
#include <node/sv2_transport.h>
#include <span.h>
#include <sync.h>
#include <tinyformat.h>
#include <util/string.h>

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace node {
namespace {
constexpr uint32_t TYPE_FIELD_SIZE{1};
constexpr uint32_t SEQUENCE_FIELD_SIZE{8};

std::vector<uint8_t> ToBytes(const std::string& str)
{
    return std::vector<uint8_t>(str.begin(), str.end());
}

std::vector<uint8_t> SerializeNewTemplate(const interfaces::NewTemplate& update)
{
    return ToBytes(strprintf("tip=%s;nbits=%08x;mempool_seq=%u",
                             update.tip_hash.GetHex(),
                             update.n_bits,
                             update.tx_updated_count));
}

std::vector<uint8_t> SerializeSetNewPrevHash(const interfaces::SetNewPrevHash& update)
{
    std::vector<std::string> parent_hashes;
    parent_hashes.reserve(update.mining_parents.size());
    for (const auto& hash : update.mining_parents) {
        parent_hashes.push_back(hash.GetHex());
    }
    return ToBytes(strprintf("tip=%s;parents=%s",
                             update.tip_hash.GetHex(),
                             util::Join(parent_hashes, ",")));
}

uint32_t ReadBE32(Span<const uint8_t> bytes)
{
    return (uint32_t{bytes[0]} << 24) | (uint32_t{bytes[1]} << 16) | (uint32_t{bytes[2]} << 8) | uint32_t{bytes[3]};
}

} // namespace

SV2Transport::SV2Transport(interfaces::Mining& mining) : m_mining(mining) {}

SV2Transport::~SV2Transport()
{
    Stop();
}

bool SV2Transport::Start()
{
    LOCK(m_mutex);
    if (m_running) return false;

    m_new_template_handler = m_mining.handleNewTemplate([this](const interfaces::NewTemplate& update) {
        OnNewTemplate(update);
    });
    m_set_new_prev_hash_handler = m_mining.handleSetNewPrevHash([this](const interfaces::SetNewPrevHash& update) {
        OnSetNewPrevHash(update);
    });
    m_running = true;
    return true;
}

void SV2Transport::Stop()
{
    LOCK(m_mutex);
    if (m_new_template_handler) m_new_template_handler->disconnect();
    if (m_set_new_prev_hash_handler) m_set_new_prev_hash_handler->disconnect();
    m_new_template_handler.reset();
    m_set_new_prev_hash_handler.reset();
    m_running = false;
}

bool SV2Transport::IsRunning() const
{
    LOCK(m_mutex);
    return m_running;
}

void SV2Transport::OnClientConnected(uint64_t client_id)
{
    LOCK(m_mutex);
    (void)m_clients.try_emplace(client_id);
}

void SV2Transport::OnClientDisconnected(uint64_t client_id)
{
    LOCK(m_mutex);
    m_clients.erase(client_id);
}

void SV2Transport::OnClientBytes(uint64_t client_id, Span<const uint8_t> bytes)
{
    LOCK(m_mutex);
    auto it = m_clients.find(client_id);
    if (it == m_clients.end()) {
        it = m_clients.try_emplace(client_id).first;
    }
    it->second.rx_buffer.insert(it->second.rx_buffer.end(), bytes.begin(), bytes.end());
    ParseClientFrames(client_id);
}

std::vector<std::vector<uint8_t>> SV2Transport::DrainOutboundFrames(uint64_t client_id)
{
    LOCK(m_mutex);
    std::vector<std::vector<uint8_t>> out;
    auto it = m_clients.find(client_id);
    if (it == m_clients.end()) return out;

    out.reserve(it->second.outbound_frames.size());
    while (!it->second.outbound_frames.empty()) {
        out.push_back(std::move(it->second.outbound_frames.front()));
        it->second.outbound_frames.pop_front();
    }
    return out;
}

std::vector<std::vector<uint8_t>> SV2Transport::DrainSubmitFrames(uint64_t client_id)
{
    LOCK(m_mutex);
    std::vector<std::vector<uint8_t>> out;
    auto it = m_clients.find(client_id);
    if (it == m_clients.end()) return out;

    out.reserve(it->second.submit_frames.size());
    while (!it->second.submit_frames.empty()) {
        out.push_back(std::move(it->second.submit_frames.front()));
        it->second.submit_frames.pop_front();
    }
    return out;
}

SV2TransportStats SV2Transport::GetStats() const
{
    LOCK(m_mutex);
    SV2TransportStats stats;
    stats.running = m_running;
    stats.connected_clients = m_clients.size();
    stats.next_sequence = m_next_sequence;
    for (const auto& [_, client] : m_clients) {
        stats.queued_outbound_frames += client.outbound_frames.size();
        stats.queued_submit_frames += client.submit_frames.size();
    }
    return stats;
}

void SV2Transport::OnNewTemplate(const interfaces::NewTemplate& update)
{
    LOCK(m_mutex);
    if (!m_running) return;
    BroadcastFrame(SV2MessageType::NEW_TEMPLATE, SerializeNewTemplate(update));
}

void SV2Transport::OnSetNewPrevHash(const interfaces::SetNewPrevHash& update)
{
    LOCK(m_mutex);
    if (!m_running) return;
    BroadcastFrame(SV2MessageType::SET_NEW_PREV_HASH, SerializeSetNewPrevHash(update));
}

void SV2Transport::ParseClientFrames(uint64_t client_id)
{
    auto it = m_clients.find(client_id);
    if (it == m_clients.end()) return;
    ClientState& client = it->second;

    while (client.rx_buffer.size() >= 4) {
        const uint32_t frame_size = ReadBE32(Span<const uint8_t>{client.rx_buffer}.first(4));
        if (frame_size == 0 || frame_size > MAX_FRAME_SIZE) {
            LogPrint(BCLog::NET,
                     "SV2 transport: dropping client=%llu buffer due to invalid frame size=%u\n",
                     static_cast<unsigned long long>(client_id), frame_size);
            client.rx_buffer.clear();
            return;
        }
        if (client.rx_buffer.size() < 4 + frame_size) return;

        std::vector<uint8_t> frame(frame_size);
        std::copy_n(client.rx_buffer.begin() + 4, frame_size, frame.begin());
        HandleInboundFrame(client, frame);
        client.rx_buffer.erase(client.rx_buffer.begin(), client.rx_buffer.begin() + 4 + frame_size);
    }
}

void SV2Transport::HandleInboundFrame(ClientState& client, Span<const uint8_t> frame)
{
    if (frame.empty()) return;
    const auto type = static_cast<SV2MessageType>(frame.front());
    if (type == SV2MessageType::SUBMIT_SOLUTION) {
        std::vector<uint8_t> payload;
        payload.reserve(frame.size() - 1);
        payload.insert(payload.end(), frame.begin() + 1, frame.end());
        client.submit_frames.push_back(std::move(payload));
    }
}

void SV2Transport::BroadcastFrame(SV2MessageType type, const std::vector<uint8_t>& payload)
{
    const uint64_t sequence = m_next_sequence++;
    const std::vector<uint8_t> encoded = EncodeFrame(type, sequence, payload);
    for (auto& [_, client] : m_clients) {
        client.outbound_frames.push_back(encoded);
    }
}

std::vector<uint8_t> SV2Transport::EncodeFrame(SV2MessageType type, uint64_t sequence, const std::vector<uint8_t>& payload)
{
    const uint32_t frame_size = TYPE_FIELD_SIZE + SEQUENCE_FIELD_SIZE + payload.size();
    std::vector<uint8_t> out;
    out.reserve(4 + frame_size);

    out.push_back((frame_size >> 24) & 0xff);
    out.push_back((frame_size >> 16) & 0xff);
    out.push_back((frame_size >> 8) & 0xff);
    out.push_back(frame_size & 0xff);
    out.push_back(static_cast<uint8_t>(type));
    for (int i = 7; i >= 0; --i) {
        out.push_back((sequence >> (i * 8)) & 0xff);
    }
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}

} // namespace node
