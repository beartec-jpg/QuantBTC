// Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT.
require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const DEPLOYER_KEY = process.env.DEPLOYER_PRIVATE_KEY || "0x" + "0".repeat(64);
const ETHERSCAN_KEY = process.env.ETHERSCAN_API_KEY || "";
const INFURA_KEY  = process.env.INFURA_PROJECT_ID   || "";

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      // Enable the IR-based code generator for better optimization and
      // compatibility with stack-depth-heavy contracts.
      viaIR: true,
    },
  },
  networks: {
    // ── Local development ──────────────────────────────────────────────────
    hardhat: {
      chainId: 31337,
    },
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },

    // ── Ethereum Sepolia testnet ───────────────────────────────────────────
    sepolia: {
      url: `https://sepolia.infura.io/v3/${INFURA_KEY}`,
      chainId: 11155111,
      accounts: [DEPLOYER_KEY],
      gasPrice: "auto",
    },

    // ── Ethereum mainnet ───────────────────────────────────────────────────
    // Only deploy after completing the mainnet-deployment checklist in
    // contrib/evm-htlc/README.md.
    mainnet: {
      url: `https://mainnet.infura.io/v3/${INFURA_KEY}`,
      chainId: 1,
      accounts: [DEPLOYER_KEY],
      gasPrice: "auto",
    },
  },
  etherscan: {
    apiKey: ETHERSCAN_KEY,
  },
  gasReporter: {
    enabled: process.env.REPORT_GAS !== undefined,
    currency: "USD",
  },
};
