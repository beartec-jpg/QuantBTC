// Copyright (c) 2024 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_INTERFACES_MINING_H
#define BITCOIN_INTERFACES_MINING_H

#include <node/types.h>
#include <uint256.h>

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <vector>

namespace node {
struct CBlockTemplate;
struct NodeContext;
} // namespace node

class BlockValidationState;
class CBlock;
class CScript;

namespace interfaces {

//! Interface giving clients (RPC, Stratum v2 Template Provider in the future)
//! ability to create block templates.

class Handler;

struct NewTemplate
{
    uint256 tip_hash;
    uint32_t n_bits{0};
    //! Mempool update sequence; 0 when mempool context is unavailable.
    unsigned int tx_updated_count{0};
};

struct SetNewPrevHash
{
    uint256 tip_hash;
    std::vector<uint256> mining_parents;
};

using NewTemplateFn = std::function<void(const NewTemplate&)>;
using SetNewPrevHashFn = std::function<void(const SetNewPrevHash&)>;

class Mining
{
public:
    virtual ~Mining() = default;

    //! If this chain is exclusively used for testing
    virtual bool isTestChain() = 0;

    //! Returns whether IBD is still in progress.
    virtual bool isInitialBlockDownload() = 0;

    //! Returns the hash for the tip of this chain
    virtual std::optional<uint256> getTipHash() = 0;

   /**
     * Construct a new block template
     *
     * @param[in] script_pub_key the coinbase output
     * @param[in] options options for creating the block
     * @returns a block template
     */
    virtual std::unique_ptr<node::CBlockTemplate> createNewBlock(const CScript& script_pub_key, const node::BlockCreateOptions& options={}) = 0;

    /**
     * Processes new block. A valid new block is automatically relayed to peers.
     *
     * @param[in]   block The block we want to process.
     * @param[out]  new_block A boolean which is set to indicate if the block was first received via this call
     * @returns     If the block was processed, independently of block validity
     */
    virtual bool processNewBlock(const std::shared_ptr<const CBlock>& block, bool* new_block) = 0;

    //! Return the number of transaction updates in the mempool,
    //! used to decide whether to make a new block template.
    virtual unsigned int getTransactionsUpdated() = 0;

    //! Register callback to receive SV2-style NewTemplate notifications.
    virtual std::unique_ptr<Handler> handleNewTemplate(NewTemplateFn fn) = 0;

    //! Register callback to receive SV2-style SetNewPrevHash notifications.
    virtual std::unique_ptr<Handler> handleSetNewPrevHash(SetNewPrevHashFn fn) = 0;

    //! Process an SV2-style solution submission.
    virtual bool submitSolution(const std::shared_ptr<const CBlock>& block, bool* new_block) = 0;

    //! Return latest SV2-style prevhash update snapshot.
    virtual std::optional<SetNewPrevHash> getSetNewPrevHash() = 0;

    /**
     * Check a block is completely valid from start to finish.
     * Only works on top of our current best block.
     * Does not check proof-of-work.
     *
     * @param[in] block the block to validate
     * @param[in] check_merkle_root call CheckMerkleRoot()
     * @param[out] state details of why a block failed to validate
     * @returns false if it does not build on the current tip, or any of the checks fail
     */
    virtual bool testBlockValidity(const CBlock& block, bool check_merkle_root, BlockValidationState& state) = 0;

    //! Get internal node context. Useful for RPC and testing,
    //! but not accessible across processes.
    virtual node::NodeContext* context() { return nullptr; }
};

//! Return implementation of Mining interface.
std::unique_ptr<Mining> MakeMining(node::NodeContext& node);

} // namespace interfaces

#endif // BITCOIN_INTERFACES_MINING_H
