# **pqc-bitcoin**

This repository is the result of a collaborative effort between [QBlock](https://link-to-qblock-account) & [Qbits](https://link-to-qbits-account), working together to build a future-proof version of Bitcoin Core that can withstand the potential threats posed by quantum computers. The integration of Post-Quantum Cryptography (PQC) algorithms into Bitcoin Core is a key initiative in ensuring that Bitcoin remains secure in the advent of quantum computing.

Quantum computing represents a breakthrough in computational capabilities, but it also poses a significant risk to current cryptographic techniques, including the elliptic curve cryptography (ECC) widely used in Bitcoin today. These classical encryption methods could potentially be broken by powerful quantum computers, leading to vulnerabilities in blockchain technologies. To mitigate this, the integration of quantum-resistant algorithms into Bitcoin Core is imperative.


## **Overview**

Quantum computing poses a potential threat to current cryptographic methods, including those used in Bitcoin, like elliptic curve cryptography (ECC). This project investigates incorporating post-quantum cryptographic algorithms to secure Bitcoin transactions and wallets in the event of future quantum attacks.

The goal is to make Bitcoin Core quantum-resistant by adopting algorithms that remain secure even in a world with powerful quantum computers.

## **Features**

- **Integration of PQC Algorithms**: Implements quantum-safe cryptographic algorithms alongside existing Bitcoin protocols.
- **Quantum-Resistant Wallets**: Modify Bitcoin Core's wallet functionality to utilize PQC keys for enhanced security.
- **Backward Compatibility**: Maintain compatibility with Bitcoin's current cryptographic algorithms for users not yet ready to switch to PQC.

## **Current PQC Algorithms Implemented**

- **Kyber**: A lattice-based key encapsulation mechanism (KEM) for public-key encryption.
- **FrodoKEM**: A key encapsulation mechanism based on the hardness of the learning with errors (LWE) problem.
- **NTRU**: A lattice-based public-key cryptosystem designed to be secure against quantum computers.

These algorithms are integrated into the Bitcoin codebase in a way that ensures both backward and forward compatibility with existing Bitcoin infrastructure.

## **Installation**

To build and test the PQC-enabled Bitcoin Core:

### **Clone the repository:**

```bash
git clone https://github.com/your-username/pqc-bitcoin.git
cd pqc-bitcoin
```

## Install Dependencies

Before building Bitcoin Core with PQC integration, install the necessary dependencies
```bash
sudo apt-get update
sudo apt-get install build-essential libtool autotools-dev automake pkg-config bsdmainutils curl
sudo apt-get install libssl-dev libevent-dev libboost-all-dev libdb-dev libdb++-dev libminiupnpc-dev
```

## Build Bitcoin Core

Once the dependencies are installed, you can build Bitcoin Core with PQC support
```bash
./autogen.sh
./configure --without-gui
make
```

## Run PQC Bitcoin Core

After building Bitcoin Core, you can run the PQC-enabled Bitcoin Core in regtest mode for testing
```bash
./src/bitcoind -regtest
```

## Testing PQC Bitcoin

The test framework ensures that the PQC algorithms integrate smoothly with Bitcoin Core’s existing features.
For detailed testing instructions, refer to the Bitcoin Test Suite.

## To run tests:
```bash
make check
```

## Validate PQC Key Generation: Test key generation using PQC algorithms
```bash
./src/bitcoin-cli pqc-keygen
```

## Contributions

We welcome contributions to make Bitcoin Core quantum-resistant. Feel free to fork this repository and submit pull requests.

For discussions and issues, please open an issue on the GitHub repository.

## License

This project is licensed under the MIT License. **Made with love by [QBlock](https://link-to-qblock-account) & [Qbits](https://link-to-qbits-account)** 💖


