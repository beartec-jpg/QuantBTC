// Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT.
// Deploy script for QBTCUSDCHTLC.
//
// Usage:
//   npm run deploy:sepolia   — deploy to Ethereum Sepolia
//   npm run deploy:mainnet   — deploy to Ethereum mainnet (after checklist)
//
// Required environment variables (copy .env.example → .env):
//   DEPLOYER_PRIVATE_KEY   — hex private key of the deployer account
//   USDC_TOKEN_ADDRESS     — USDC contract address on the target network
//   INFURA_PROJECT_ID      — Infura project ID for RPC access
//   ETHERSCAN_API_KEY      — for automatic source verification on Etherscan
//
// USDC addresses:
//   Sepolia:  0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238
//   Mainnet:  0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48

const hre = require("hardhat");

// Known USDC addresses by chainId.
const KNOWN_USDC = {
  11155111: "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238", // Sepolia
  1:        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", // Mainnet
};

async function main() {
  const { ethers, network } = hre;
  const chainId = network.config.chainId;

  console.log(`\n=== QBTC USDC HTLC Deployment ===`);
  console.log(`Network : ${network.name} (chainId ${chainId})`);

  // ── Resolve token address ──────────────────────────────────────────────
  const tokenAddress =
    process.env.USDC_TOKEN_ADDRESS ||
    KNOWN_USDC[chainId] ||
    (() => { throw new Error("USDC_TOKEN_ADDRESS not set and chainId not recognised"); })();

  console.log(`Token   : ${tokenAddress}`);

  // ── Deployer info ──────────────────────────────────────────────────────
  const [deployer] = await ethers.getSigners();
  console.log(`Deployer: ${deployer.address}`);
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Balance : ${ethers.formatEther(balance)} ETH\n`);

  // ── Guard against accidental mainnet deployment ───────────────────────
  if (chainId === 1) {
    const readline = require("readline");
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    await new Promise((resolve, reject) => {
      rl.question(
        "⚠️  You are deploying to ETHEREUM MAINNET.  Type YES to continue: ",
        (answer) => {
          rl.close();
          if (answer.trim() !== "YES") {
            reject(new Error("Mainnet deployment aborted by user."));
          } else {
            resolve();
          }
        }
      );
    });
  }

  // ── Deploy ─────────────────────────────────────────────────────────────
  console.log("Deploying QBTCUSDCHTLC...");
  const Factory = await ethers.getContractFactory("QBTCUSDCHTLC");
  const htlc = await Factory.deploy(tokenAddress);
  await htlc.waitForDeployment();

  const address = await htlc.getAddress();
  console.log(`\n✅ QBTCUSDCHTLC deployed at: ${address}`);
  console.log(`   Token (immutable)      : ${await htlc.TOKEN()}`);
  console.log(`   MIN_LOCKTIME           : ${await htlc.MIN_LOCKTIME()} seconds (${Number(await htlc.MIN_LOCKTIME()) / 3600} h)`);

  // ── Verify on Etherscan ────────────────────────────────────────────────
  if (process.env.ETHERSCAN_API_KEY && chainId !== 31337) {
    console.log("\nWaiting 6 confirmations before verifying on Etherscan...");
    await htlc.deploymentTransaction().wait(6);

    try {
      await hre.run("verify:verify", {
        address: address,
        constructorArguments: [tokenAddress],
      });
      console.log("✅ Source verified on Etherscan.");
    } catch (e) {
      // Already verified or API error — not fatal.
      console.warn(`Etherscan verification: ${e.message}`);
    }
  }

  // ── Deployment summary ─────────────────────────────────────────────────
  console.log(`
=== Deployment Summary ===
Network  : ${network.name}
Contract : ${address}
Token    : ${tokenAddress}
Deployer : ${deployer.address}
Block    : ${(await htlc.deploymentTransaction().wait()).blockNumber}

Update ATOMIC-SWAP-REPORT.md and SECURITY.md with the new contract address.
Update the swap server environment variable HTLC_CONTRACT_ADDRESS.
`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
