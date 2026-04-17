# QBTC ↔ USDC Atomic Swap — EVM HTLC

Fixed and audited Solidity contract for the Ethereum leg of QBTC ↔ USDC
cross-chain atomic swaps (internal audit 2026-04-17).

## Quick start

```bash
cd contrib/evm-htlc
npm install
npx hardhat compile
npx hardhat test
```

## Deployment — Sepolia (testnet reset)

```bash
cp .env.example .env
# fill in DEPLOYER_PRIVATE_KEY, INFURA_PROJECT_ID, ETHERSCAN_API_KEY
npm run deploy:sepolia
```

The script prints the deployed contract address.  Update:
- `ATOMIC-SWAP-REPORT.md` — Contract Address row
- `SECURITY.md` — contract address in the Known Design Limitations section
- Swap server env var `HTLC_CONTRACT_ADDRESS`

## Audit Fixes (vs previous contract `0xaF898a5F565c0cAE1746122ad475c0B7F160A3eb`)

| ID  | Severity | Finding                                       | Fix                                         |
|-----|----------|-----------------------------------------------|---------------------------------------------|
| H-1 | HIGH     | CEI violation — reentrancy in withdraw/refund | CEI order enforced + `ReentrancyGuard`      |
| H-2 | HIGH     | Must use `sha256()` not `keccak256()`         | Explicit `sha256()` with cross-chain comment|
| M-1 | MEDIUM   | approve/transferFrom race window              | `initiateWithPermit()` (EIP-2612)           |
| M-2 | MEDIUM   | No minimum timelock — immediate expiry attack | `MIN_LOCKTIME = 1 hours` enforced           |
| M-3 | MEDIUM   | contractId collision on identical params      | Per-sender nonce in contractId hash         |
| L-1 | LOW      | No zero-address / zero-amount checks          | Guards in `_initiate()`                     |
| L-2 | LOW      | Unchecked ERC-20 return values                | `SafeERC20` throughout                      |
| L-3 | LOW      | Arbitrary ERC-20 token accepted               | Immutable `TOKEN` (single-token deploy)     |
| I-1 | INFO     | No preimage zero-check                        | `revert PreimageIsZero()` guard             |
| I-2 | INFO     | Preimage not in `HTLCWithdraw` event          | `HTLCWithdraw(contractId, preimage)` emits  |
| I-3 | INFO     | No payable-fallback protection                | No `payable` functions; confirmed in tests  |

## Contract interface

```solidity
// Lock USDC (requires prior approve())
function initiate(address receiver, bytes32 hashlock, uint256 timelock, uint256 amount)
    external returns (bytes32 contractId);

// Lock USDC via EIP-2612 permit (single-tx, no prior approve required)
function initiateWithPermit(address receiver, bytes32 hashlock, uint256 timelock,
    uint256 amount, uint256 deadline, uint8 v, bytes32 r, bytes32 s)
    external returns (bytes32 contractId);

// Reveal preimage → receive USDC
function withdraw(bytes32 contractId, bytes32 preimage) external;

// Reclaim USDC after timelock expiry
function refund(bytes32 contractId) external;

// Read HTLC state
function getContract(bytes32 contractId) external view returns (...);
```

## Hashlock algorithm

The hashlock **must** be `sha256(preimage)` — NOT `keccak256(preimage)`.

The QBTC chain's P2WSH HTLC script uses `OP_SHA256`; the EVM contract uses
Solidity's native `sha256()` precompile (address `0x02`).  Using different
hash functions on the two chains would silently break cross-chain atomicity.

## Atomic swap timelock safety

| Chain | Timelock | Notes                                                      |
|-------|----------|------------------------------------------------------------|
| EVM   | ≥ 24 h   | Buyer can refund after this if seller never withdraws      |
| QBTC  | ≥ 48 h   | Must be **longer** than EVM timelock — protocol invariant  |

The QBTC timelock must always be strictly longer than the EVM timelock so the
seller cannot both claim USDC (revealing the secret) and refund QBTC.

## Mainnet deployment checklist

Before deploying to Ethereum mainnet, confirm all of the following:

- [ ] `sha256()` is used for hashlock verification (confirmed in source + tests)
- [ ] CEI order in `withdraw()` and `refund()` (confirmed; `ReentrancyGuard` present)
- [ ] `MIN_LOCKTIME` is at least 1 h (currently 1 h; consider 2 h for mainnet)
- [ ] `SafeERC20` wrappers on all token calls (confirmed)
- [ ] `TOKEN` is immutable and set to mainnet USDC address
- [ ] All tests pass: `npx hardhat test`
- [ ] External audit by a qualified Solidity firm (Trail of Bits / OpenZeppelin / Spearbit)
- [ ] Bytecode verified on Etherscan after deployment
- [ ] Swap server updated to use the new contract address
- [ ] Centralized secret generation moved to seller's client side (see SECURITY.md)
- [ ] Consider a deposit cap for the initial mainnet period
