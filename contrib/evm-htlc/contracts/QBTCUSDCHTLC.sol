// Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT.
// See LICENSE-BUSL and NOTICE.

// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/IERC20Permit.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title  QBTC ↔ USDC Atomic Swap HTLC
 * @notice Hash Time Lock Contract for the EVM leg of QBTC ↔ USDC cross-chain
 *         atomic swaps.  A buyer locks USDC here; the seller reveals the SHA-256
 *         preimage to claim it, simultaneously exposing the secret on-chain so
 *         the buyer can spend the QBTC HTLC (P2WSH OP_SHA256) on the QBTC chain.
 *
 * @dev    Audit fixes applied 2026-04-17 (internal audit report):
 *
 *   H-1  CEI order enforced in withdraw() and refund() + ReentrancyGuard
 *   H-2  sha256() used for hashlock — matches OP_SHA256 on QBTC chain
 *   M-1  initiateWithPermit() combines EIP-2612 permit + lock in one tx
 *   M-2  MIN_LOCKTIME constant prevents immediate-expiry griefing
 *   M-3  Per-sender nonce in contractId hash prevents duplicate-id DoS
 *   L-1  Zero-address and zero-amount validation in _initiate()
 *   L-2  SafeERC20 used for all token transfers
 *   L-3  TOKEN is immutable — single-token deployment eliminates arbitrary-
 *        token attack surface (fee-on-transfer, rebasing, malicious tokens)
 *   I-1  Preimage non-zero check in withdraw()
 *   I-2  HTLCWithdraw event includes preimage so QBTC buyer can observe it
 *   I-3  No payable functions or fallback — ETH cannot be locked here
 */
contract QBTCUSDCHTLC is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ── Constants ────────────────────────────────────────────────────────────

    /**
     * @notice Minimum timelock duration accepted by initiate().
     *         The atomic swap protocol uses 24 h for the EVM leg.  This floor
     *         of 1 h prevents a griefing attack where a buyer sets timelock to
     *         block.timestamp + 1 and immediately refunds before the seller can
     *         call withdraw().
     */
    uint256 public constant MIN_LOCKTIME = 1 hours;

    // ── Immutables ───────────────────────────────────────────────────────────

    /**
     * @notice The only ERC-20 token this contract will escrow (USDC).
     *         Hard-coded at deploy time.  Using an immutable instead of a
     *         parameter eliminates the arbitrary-token attack surface:
     *         fee-on-transfer tokens, rebasing tokens, and tokens with
     *         non-standard transfer() semantics are all excluded by design.
     */
    IERC20 public immutable TOKEN;

    // ── Data Structures ──────────────────────────────────────────────────────

    struct LockContract {
        address sender;
        address receiver;
        uint256 amount;
        /// sha256(preimage) — MUST be verified with sha256(), NOT keccak256(),
        /// to remain consistent with OP_SHA256 on the QBTC chain.
        bytes32 hashlock;
        /// Unix timestamp after which sender may call refund().
        uint256 timelock;
        bool    withdrawn;
        bool    refunded;
        /// Stored on-chain after a successful withdraw() so the QBTC buyer
        /// can observe the preimage and spend the QBTC HTLC.
        bytes32 preimage;
    }

    // ── Storage ──────────────────────────────────────────────────────────────

    /**
     * @notice Per-sender nonce, incremented each time a new HTLC is created.
     *         Included in the contractId hash to guarantee uniqueness even
     *         when all other parameters (amount, receiver, hashlock, timelock)
     *         are identical across multiple swaps.
     */
    mapping(address => uint256) public nonces;

    /// @dev HTLC records keyed by contractId.  Private — use getContract().
    mapping(bytes32 => LockContract) private _contracts;

    // ── Events ───────────────────────────────────────────────────────────────

    /**
     * @notice Emitted when a new HTLC is created.
     * @param contractId Unique identifier for this HTLC.
     * @param sender     The party locking USDC (the swap buyer).
     * @param receiver   The party that may withdraw by revealing the preimage.
     * @param amount     USDC amount locked (in token's smallest unit, 6 decimals).
     * @param hashlock   sha256(preimage).
     * @param timelock   Unix timestamp after which sender may refund.
     */
    event HTLCInitiate(
        bytes32 indexed contractId,
        address indexed sender,
        address indexed receiver,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock
    );

    /**
     * @notice Emitted when the receiver successfully withdraws by revealing the preimage.
     * @param contractId The HTLC that was settled.
     * @param preimage   The 32-byte SHA-256 preimage.  Published here so the
     *                   QBTC buyer can read it from the chain and spend the
     *                   corresponding QBTC P2WSH HTLC output.
     */
    event HTLCWithdraw(bytes32 indexed contractId, bytes32 preimage);

    /**
     * @notice Emitted when the sender reclaims their USDC after timelock expiry.
     * @param contractId The HTLC that was refunded.
     */
    event HTLCRefund(bytes32 indexed contractId);

    // ── Custom Errors ────────────────────────────────────────────────────────

    error ContractNotFound(bytes32 contractId);
    error AlreadyWithdrawn(bytes32 contractId);
    error AlreadyRefunded(bytes32 contractId);
    error HashlockMismatch(bytes32 contractId);
    error PreimageIsZero();
    error TimelockNotExpired(bytes32 contractId);
    error TimelockExpired(bytes32 contractId);
    error TimelockTooShort(uint256 provided, uint256 minimum);
    error ZeroReceiver();
    error ZeroAmount();

    // ── Constructor ──────────────────────────────────────────────────────────

    /**
     * @param token The ERC-20 token address to escrow (USDC on the target network).
     *              Must be non-zero.
     */
    constructor(address token) {
        require(token != address(0), "HTLC: token is zero address");
        TOKEN = IERC20(token);
    }

    // ── External: HTLC initiation ────────────────────────────────────────────

    /**
     * @notice Lock `amount` USDC in a new HTLC.
     *
     * @dev Caller must have approved this contract for at least `amount` USDC
     *      before calling.  Use initiateWithPermit() to combine approval + lock
     *      in a single transaction and eliminate the approve/transferFrom race.
     *
     * @param receiver  Address that can withdraw by revealing sha256 preimage.
     * @param hashlock  sha256(preimage) — must equal the hashlock used in the
     *                  corresponding QBTC HTLC (OP_SHA256).
     * @param timelock  Unix timestamp after which sender may refund.
     *                  Must be >= block.timestamp + MIN_LOCKTIME (1 h).
     * @param amount    Amount of TOKEN to lock.
     * @return contractId  Unique HTLC identifier.
     */
    function initiate(
        address receiver,
        bytes32 hashlock,
        uint256 timelock,
        uint256 amount
    ) external nonReentrant returns (bytes32 contractId) {
        return _initiate(msg.sender, receiver, hashlock, timelock, amount);
    }

    /**
     * @notice Combine an EIP-2612 permit signature with HTLC initiation in one
     *         transaction, eliminating the approve/transferFrom front-running
     *         race window.
     *
     * @dev    The permit deadline, v, r, s parameters are forwarded directly to
     *         TOKEN.permit().  TOKEN must implement IERC20Permit (EIP-2612).
     *         USDC on both Sepolia and mainnet supports EIP-2612.
     */
    function initiateWithPermit(
        address receiver,
        bytes32 hashlock,
        uint256 timelock,
        uint256 amount,
        uint256 deadline,
        uint8   v,
        bytes32 r,
        bytes32 s
    ) external nonReentrant returns (bytes32 contractId) {
        // Grant allowance via signature — no separate approve() tx required.
        IERC20Permit(address(TOKEN)).permit(
            msg.sender, address(this), amount, deadline, v, r, s
        );
        return _initiate(msg.sender, receiver, hashlock, timelock, amount);
    }

    // ── External: HTLC settlement ────────────────────────────────────────────

    /**
     * @notice Reveal the preimage and transfer the escrowed USDC to the receiver.
     *
     * @dev    Follows Checks-Effects-Interactions:
     *           1. Checks  — validate state, preimage, hashlock, timelock
     *           2. Effects — update storage flags and store preimage
     *           3. Events  — emit before external call
     *           4. Interaction — safeTransfer to receiver
     *
     *         The preimage is emitted in HTLCWithdraw and stored in the contract
     *         record so the QBTC buyer can retrieve it from on-chain state and
     *         spend the corresponding P2WSH HTLC output on the QBTC chain.
     *
     * @param contractId  The HTLC identifier returned by initiate().
     * @param preimage    The 32-byte value whose SHA-256 hash equals hashlock.
     *                    Must be non-zero and satisfy sha256(preimage) == hashlock.
     */
    function withdraw(bytes32 contractId, bytes32 preimage) external nonReentrant {
        LockContract storage c = _contracts[contractId];

        // ── Checks ───────────────────────────────────────────────────────────
        if (c.amount == 0)         revert ContractNotFound(contractId);
        if (c.withdrawn)           revert AlreadyWithdrawn(contractId);
        if (c.refunded)            revert AlreadyRefunded(contractId);
        if (preimage == bytes32(0)) revert PreimageIsZero();
        if (block.timestamp >= c.timelock) revert TimelockExpired(contractId);

        // SHA-256 verification — MUST use sha256(), NOT keccak256().
        // The QBTC chain uses OP_SHA256 in its HTLC script; keccak256 would
        // produce a different digest and break cross-chain atomicity.
        if (c.hashlock != sha256(abi.encodePacked(preimage)))
            revert HashlockMismatch(contractId);

        // ── Effects ──────────────────────────────────────────────────────────
        address receiver = c.receiver;
        uint256 amount   = c.amount;
        c.preimage  = preimage;   // stored so QBTC buyer can read it on-chain
        c.withdrawn = true;

        // ── Events ───────────────────────────────────────────────────────────
        emit HTLCWithdraw(contractId, preimage);

        // ── Interaction ──────────────────────────────────────────────────────
        TOKEN.safeTransfer(receiver, amount);
    }

    /**
     * @notice Reclaim escrowed USDC after the timelock has expired.
     *
     * @dev    Follows Checks-Effects-Interactions (same pattern as withdraw).
     *         Only callable by anyone (not just the sender) once the timelock
     *         has passed; in practice only the sender benefits, so this is safe.
     *
     * @param contractId  The HTLC identifier returned by initiate().
     */
    function refund(bytes32 contractId) external nonReentrant {
        LockContract storage c = _contracts[contractId];

        // ── Checks ───────────────────────────────────────────────────────────
        if (c.amount == 0)  revert ContractNotFound(contractId);
        if (c.withdrawn)    revert AlreadyWithdrawn(contractId);
        if (c.refunded)     revert AlreadyRefunded(contractId);
        if (block.timestamp < c.timelock) revert TimelockNotExpired(contractId);

        // ── Effects ──────────────────────────────────────────────────────────
        address sender = c.sender;
        uint256 amount = c.amount;
        c.refunded = true;

        // ── Events ───────────────────────────────────────────────────────────
        emit HTLCRefund(contractId);

        // ── Interaction ──────────────────────────────────────────────────────
        TOKEN.safeTransfer(sender, amount);
    }

    // ── External: View ───────────────────────────────────────────────────────

    /**
     * @notice Return all fields of an HTLC record.
     * @dev    Returns zero-valued struct if contractId does not exist.
     */
    function getContract(bytes32 contractId)
        external
        view
        returns (
            address sender,
            address receiver,
            uint256 amount,
            bytes32 hashlock,
            uint256 timelock,
            bool    withdrawn,
            bool    refunded,
            bytes32 preimage
        )
    {
        LockContract storage c = _contracts[contractId];
        return (
            c.sender,
            c.receiver,
            c.amount,
            c.hashlock,
            c.timelock,
            c.withdrawn,
            c.refunded,
            c.preimage
        );
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    /**
     * @dev Core initiation logic shared by initiate() and initiateWithPermit().
     *      Validates inputs, writes storage, emits event, then transfers tokens
     *      (CEI order maintained).
     */
    function _initiate(
        address sender,
        address receiver,
        bytes32 hashlock,
        uint256 timelock,
        uint256 amount
    ) internal returns (bytes32 contractId) {
        // ── Checks ───────────────────────────────────────────────────────────
        if (receiver == address(0)) revert ZeroReceiver();
        if (amount == 0)            revert ZeroAmount();
        if (timelock < block.timestamp + MIN_LOCKTIME)
            revert TimelockTooShort(
                timelock > block.timestamp ? timelock - block.timestamp : 0,
                MIN_LOCKTIME
            );

        // Derive a unique contractId using a per-sender nonce so that identical
        // swap parameters (same amount, receiver, hashlock, timelock) across
        // repeated swaps always produce distinct identifiers.
        // Read-then-increment to keep the state change explicit and auditable.
        uint256 nonce = nonces[sender]++;
        contractId = keccak256(
            abi.encodePacked(
                sender,
                receiver,
                amount,
                hashlock,
                timelock,
                nonce
            )
        );

        // Belt-and-suspenders: contractId must not already exist.
        require(_contracts[contractId].amount == 0, "HTLC: contractId collision");

        // ── Effects ──────────────────────────────────────────────────────────
        _contracts[contractId] = LockContract({
            sender:    sender,
            receiver:  receiver,
            amount:    amount,
            hashlock:  hashlock,
            timelock:  timelock,
            withdrawn: false,
            refunded:  false,
            preimage:  bytes32(0)
        });

        // ── Events ───────────────────────────────────────────────────────────
        emit HTLCInitiate(contractId, sender, receiver, amount, hashlock, timelock);

        // ── Interaction ──────────────────────────────────────────────────────
        TOKEN.safeTransferFrom(sender, address(this), amount);
    }
}
