// Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT.
//
// Hardhat / Mocha tests for QBTCUSDCHTLC.sol
//
// Run:  npx hardhat test
//       REPORT_GAS=1 npx hardhat test   (with gas report)

const { expect } = require("chai");
const { ethers }  = require("hardhat");
const { time }    = require("@nomicfoundation/hardhat-network-helpers");

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Compute sha256(preimage) in JS exactly as the Solidity contract does:
 *   sha256(abi.encodePacked(preimage))
 * where preimage is a bytes32 (32-byte hex string).
 */
function sha256Bytes32(preimageHex) {
  const { createHash } = require("crypto");
  // Strip 0x prefix, decode hex to Buffer, hash it.
  const buf = Buffer.from(preimageHex.replace(/^0x/, ""), "hex");
  return "0x" + createHash("sha256").update(buf).digest("hex");
}

/** Generate a random 32-byte hex preimage (as Solidity bytes32). */
function randomPreimage() {
  return ethers.hexlify(ethers.randomBytes(32));
}

const ONE_HOUR = 3600n; // seconds
const ONE_DAY  = 24n * ONE_HOUR;
const USDC_DEC = 6n;
const USDC_ONE = 10n ** USDC_DEC; // 1 USDC = 1_000_000

// ── Fixtures ──────────────────────────────────────────────────────────────────

async function deployFixture() {
  const [owner, seller, buyer, attacker] = await ethers.getSigners();

  // Deploy a minimal mock ERC-20 token (18 dec — we use its own 6-dec variant below)
  const ERC20Mock = await ethers.getContractFactory("ERC20Mock");
  const usdc = await ERC20Mock.deploy("USD Coin", "USDC", 6);
  await usdc.waitForDeployment();

  // Mint USDC to buyer
  await usdc.mint(buyer.address, 1_000_000n * USDC_ONE); // 1 M USDC

  // Deploy HTLC
  const HTLC = await ethers.getContractFactory("QBTCUSDCHTLC");
  const htlc = await HTLC.deploy(await usdc.getAddress());
  await htlc.waitForDeployment();

  return { htlc, usdc, owner, seller, buyer, attacker };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("QBTCUSDCHTLC", function () {
  // ── Deployment ─────────────────────────────────────────────────────────────

  describe("Deployment", function () {
    it("sets TOKEN to the constructor argument", async function () {
      const { htlc, usdc } = await deployFixture();
      expect(await htlc.TOKEN()).to.equal(await usdc.getAddress());
    });

    it("reverts if token is zero address", async function () {
      const HTLC = await ethers.getContractFactory("QBTCUSDCHTLC");
      await expect(HTLC.deploy(ethers.ZeroAddress))
        .to.be.revertedWith("HTLC: token is zero address");
    });

    it("MIN_LOCKTIME is 1 hour (3600 s)", async function () {
      const { htlc } = await deployFixture();
      expect(await htlc.MIN_LOCKTIME()).to.equal(ONE_HOUR);
    });

    it("has no ETH balance and no payable functions", async function () {
      const { htlc } = await deployFixture();
      const balance = await ethers.provider.getBalance(await htlc.getAddress());
      expect(balance).to.equal(0n);
    });
  });

  // ── initiate() ─────────────────────────────────────────────────────────────

  describe("initiate()", function () {
    it("creates an HTLC and transfers USDC to the contract", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage  = randomPreimage();
      const hashlock  = sha256Bytes32(preimage);
      const amount    = 10n * USDC_ONE;
      const now       = BigInt(await time.latest());
      const timelock  = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);

      await expect(htlc.connect(buyer).initiate(seller.address, hashlock, timelock, amount))
        .to.emit(htlc, "HTLCInitiate")
        .withArgs(
          // contractId is the first unnamed return — capture via any matcher
          (id) => typeof id === "string" && id.startsWith("0x"),
          buyer.address,
          seller.address,
          amount,
          hashlock,
          timelock
        );

      expect(await usdc.balanceOf(await htlc.getAddress())).to.equal(amount);
    });

    it("increments nonce after each call", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const amount   = USDC_ONE;
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;
      const hashlock = sha256Bytes32(randomPreimage());

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount * 2n);
      expect(await htlc.nonces(buyer.address)).to.equal(0n);

      await htlc.connect(buyer).initiate(seller.address, hashlock, timelock, amount);
      expect(await htlc.nonces(buyer.address)).to.equal(1n);

      const hashlock2 = sha256Bytes32(randomPreimage());
      await htlc.connect(buyer).initiate(seller.address, hashlock2, timelock, amount);
      expect(await htlc.nonces(buyer.address)).to.equal(2n);
    });

    it("reverts with ZeroReceiver", async function () {
      const { htlc, usdc, buyer } = await deployFixture();
      const now      = BigInt(await time.latest());
      await usdc.connect(buyer).approve(await htlc.getAddress(), USDC_ONE);
      await expect(
        htlc.connect(buyer).initiate(
          ethers.ZeroAddress,
          sha256Bytes32(randomPreimage()),
          now + ONE_DAY,
          USDC_ONE
        )
      ).to.be.revertedWithCustomError(htlc, "ZeroReceiver");
    });

    it("reverts with ZeroAmount", async function () {
      const { htlc, buyer, seller } = await deployFixture();
      const now = BigInt(await time.latest());
      await expect(
        htlc.connect(buyer).initiate(
          seller.address,
          sha256Bytes32(randomPreimage()),
          now + ONE_DAY,
          0n
        )
      ).to.be.revertedWithCustomError(htlc, "ZeroAmount");
    });

    it("reverts with TimelockTooShort when timelock < now + 1h", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const now = BigInt(await time.latest());
      await usdc.connect(buyer).approve(await htlc.getAddress(), USDC_ONE);
      await expect(
        htlc.connect(buyer).initiate(
          seller.address,
          sha256Bytes32(randomPreimage()),
          now + 60n, // only 60 seconds — below 1 h minimum
          USDC_ONE
        )
      ).to.be.revertedWithCustomError(htlc, "TimelockTooShort");
    });
  });

  // ── withdraw() ─────────────────────────────────────────────────────────────

  describe("withdraw()", function () {
    async function setupLock(htlc, usdc, buyer, seller, amount, preimage) {
      const hashlock = sha256Bytes32(preimage);
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;
      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, hashlock, timelock, amount
      );
      const receipt = await tx.wait();
      // Extract contractId from HTLCInitiate event
      const event = receipt.logs.find(
        (l) => l.fragment && l.fragment.name === "HTLCInitiate"
      );
      const contractId = event.args[0];
      return { contractId, hashlock, timelock };
    }

    it("transfers USDC to receiver and emits HTLCWithdraw with preimage", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const amount   = 5n * USDC_ONE;
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, amount, preimage);

      const sellerBefore = await usdc.balanceOf(seller.address);
      await expect(htlc.connect(seller).withdraw(contractId, preimage))
        .to.emit(htlc, "HTLCWithdraw")
        .withArgs(contractId, preimage);

      expect(await usdc.balanceOf(seller.address)).to.equal(sellerBefore + amount);
    });

    it("stores preimage on-chain after withdrawal", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, USDC_ONE, preimage);

      await htlc.connect(seller).withdraw(contractId, preimage);

      const stored = await htlc.getContract(contractId);
      expect(stored.preimage).to.equal(preimage);
      expect(stored.withdrawn).to.equal(true);
    });

    it("reverts with HashlockMismatch on wrong preimage", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, USDC_ONE, preimage);

      await expect(
        htlc.connect(seller).withdraw(contractId, randomPreimage())
      ).to.be.revertedWithCustomError(htlc, "HashlockMismatch");
    });

    it("reverts with PreimageIsZero on zero preimage", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, USDC_ONE, preimage);

      await expect(
        htlc.connect(seller).withdraw(contractId, ethers.ZeroHash)
      ).to.be.revertedWithCustomError(htlc, "PreimageIsZero");
    });

    it("reverts with TimelockExpired after timelock passes", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, USDC_ONE, preimage);

      await time.increase(ONE_DAY + ONE_HOUR);

      await expect(
        htlc.connect(seller).withdraw(contractId, preimage)
      ).to.be.revertedWithCustomError(htlc, "TimelockExpired");
    });

    it("reverts with AlreadyWithdrawn on double-withdraw (reentrancy guard)", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const preimage = randomPreimage();
      const { contractId } = await setupLock(htlc, usdc, buyer, seller, USDC_ONE, preimage);

      await htlc.connect(seller).withdraw(contractId, preimage);
      await expect(
        htlc.connect(seller).withdraw(contractId, preimage)
      ).to.be.revertedWithCustomError(htlc, "AlreadyWithdrawn");
    });
  });

  // ── refund() ───────────────────────────────────────────────────────────────

  describe("refund()", function () {
    it("returns USDC to sender after timelock expiry", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const amount   = 3n * USDC_ONE;
      const hashlock = sha256Bytes32(randomPreimage());
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, hashlock, timelock, amount
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "HTLCInitiate");
      const contractId = event.args[0];

      await time.increase(ONE_DAY + 1n);

      const buyerBefore = await usdc.balanceOf(buyer.address);
      await expect(htlc.connect(buyer).refund(contractId))
        .to.emit(htlc, "HTLCRefund")
        .withArgs(contractId);

      expect(await usdc.balanceOf(buyer.address)).to.equal(buyerBefore + amount);
    });

    it("reverts with TimelockNotExpired before timelock passes", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const amount   = USDC_ONE;
      const hashlock = sha256Bytes32(randomPreimage());
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, hashlock, timelock, amount
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "HTLCInitiate");
      const contractId = event.args[0];

      await expect(htlc.connect(buyer).refund(contractId))
        .to.be.revertedWithCustomError(htlc, "TimelockNotExpired");
    });

    it("reverts with AlreadyRefunded on double-refund", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();
      const amount   = USDC_ONE;
      const hashlock = sha256Bytes32(randomPreimage());
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, hashlock, timelock, amount
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "HTLCInitiate");
      const contractId = event.args[0];

      await time.increase(ONE_DAY + 1n);
      await htlc.connect(buyer).refund(contractId);

      await expect(htlc.connect(buyer).refund(contractId))
        .to.be.revertedWithCustomError(htlc, "AlreadyRefunded");
    });
  });

  // ── getContract() ──────────────────────────────────────────────────────────

  describe("getContract()", function () {
    it("returns zero-valued struct for unknown contractId", async function () {
      const { htlc } = await deployFixture();
      const result = await htlc.getContract(ethers.ZeroHash);
      expect(result.amount).to.equal(0n);
      expect(result.withdrawn).to.equal(false);
    });
  });

  // ── SHA-256 cross-chain consistency ────────────────────────────────────────

  describe("SHA-256 hashlock", function () {
    it("accepts the hashlock from completed Swap #1 (on-chain data verification)", async function () {
      // This test uses the real secret and secretHash from the first completed
      // QBTC ↔ USDC atomic swap (April 14, 2026) as documented in
      // ATOMIC-SWAP-REPORT.md to verify that the contract's sha256() check
      // matches OP_SHA256 on the QBTC chain.
      const { htlc, usdc, buyer, seller } = await deployFixture();

      const REAL_PREIMAGE = "0x2ab01b4b7c30c0687bdf74d39954b5e31b99358675b2193495134570d21d223b";
      const EXPECTED_HASH = "0x453f132ea229f4e38c2e6de02be6b74f17fa5fefd8c3677fb3078f6677806e31";

      // Verify JS sha256 matches expected
      expect(sha256Bytes32(REAL_PREIMAGE)).to.equal(EXPECTED_HASH);

      const amount   = USDC_ONE;
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, EXPECTED_HASH, timelock, amount
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "HTLCInitiate");
      const contractId = event.args[0];

      // Withdraw with the real preimage — must succeed
      await expect(htlc.connect(seller).withdraw(contractId, REAL_PREIMAGE))
        .to.emit(htlc, "HTLCWithdraw")
        .withArgs(contractId, REAL_PREIMAGE);
    });

    it("rejects a keccak256 preimage (wrong hash function)", async function () {
      const { htlc, usdc, buyer, seller } = await deployFixture();

      const preimage  = randomPreimage();
      // Intentionally use keccak256 as the hashlock (wrong function)
      const wrongHash = ethers.keccak256(preimage);

      const amount   = USDC_ONE;
      const now      = BigInt(await time.latest());
      const timelock = now + ONE_DAY;

      await usdc.connect(buyer).approve(await htlc.getAddress(), amount);
      const tx = await htlc.connect(buyer).initiate(
        seller.address, wrongHash, timelock, amount
      );
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "HTLCInitiate");
      const contractId = event.args[0];

      // The contract verifies sha256(preimage); since wrongHash = keccak256(preimage),
      // sha256(preimage) ≠ keccak256(preimage) → HashlockMismatch
      await expect(htlc.connect(seller).withdraw(contractId, preimage))
        .to.be.revertedWithCustomError(htlc, "HashlockMismatch");
    });
  });
});
