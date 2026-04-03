#!/usr/bin/env python3
# Copyright (c) 2024 The QuantumBTC developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test PQC (Post-Quantum Cryptography) witness transaction handling.

Verifies that the script interpreter correctly processes and rejects
PQC-extended P2WPKH witness stacks (4-element: ecdsa_sig, pubkey,
pqc_sig, pqc_pubkey) with appropriate error codes for:
  - Dilithium key/signature size mismatches
  - SPHINCS+ key/signature size mismatches
  - Unsupported PQC algorithm sizes
  - Malformed PQC witness data
"""

from decimal import Decimal

from test_framework.messages import (
    tx_from_hex,
)
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_raises_rpc_error

# ML-DSA-44 (Dilithium2) sizes
DILITHIUM_PK_SIZE = 1312
DILITHIUM_SIG_SIZE = 2420

# SLH-DSA-SHA2-128f (SPHINCS+) sizes
SPHINCS_PK_SIZE = 32
SPHINCS_SIG_SIZE = 17088


class PQCWitnessTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 1
        self.extra_args = [[]]

    def skip_test_if_missing_module(self):
        self.skip_if_no_wallet()

    def _fund_and_get_utxo(self, node):
        """Mine some blocks and get a spendable UTXO via P2WPKH."""
        addr = node.getnewaddress("", "bech32")
        self.generatetoaddress(node, 101, addr)

        # Find a spendable UTXO
        utxos = node.listunspent(1, 9999999, [addr])
        assert len(utxos) > 0, "No spendable UTXOs found"
        utxo = utxos[0]
        return utxo, addr

    def _create_spending_tx(self, node, utxo, pqc_sig, pqc_pubkey):
        """Create a raw transaction that spends a P2WPKH UTXO with a
        4-element PQC-extended witness stack.

        The witness stack will be: [ecdsa_sig, compressed_pubkey, pqc_sig, pqc_pubkey]
        """
        # Create a destination address
        dest_addr = node.getnewaddress("", "bech32")

        # Use createrawtransaction to build the spending tx
        amount = Decimal(str(utxo["amount"])) - Decimal("0.001")
        raw_tx = node.createrawtransaction(
            [{"txid": utxo["txid"], "vout": utxo["vout"]}],
            {dest_addr: str(amount)},
        )

        # Sign with ECDSA first (this gives us the standard 2-element witness)
        signed = node.signrawtransactionwithwallet(raw_tx)
        assert signed["complete"], "ECDSA signing failed"
        tx_hex = signed["hex"]

        # Deserialize, inject PQC witness elements, re-serialize
        tx = tx_from_hex(tx_hex)

        # The standard witness has [ecdsa_sig, pubkey].
        # We extend it to [ecdsa_sig, pubkey, pqc_sig, pqc_pubkey].
        if tx.wit.vtxinwit and tx.wit.vtxinwit[0].scriptWitness.stack:
            original_stack = tx.wit.vtxinwit[0].scriptWitness.stack
            assert len(original_stack) == 2, (
                f"Expected 2-element witness, got {len(original_stack)}"
            )
            # Append PQC signature and public key to the witness stack
            tx.wit.vtxinwit[0].scriptWitness.stack = [
                original_stack[0],   # ecdsa_sig
                original_stack[1],   # compressed pubkey
                pqc_sig,             # PQC signature
                pqc_pubkey,          # PQC public key
            ]

        tx.rehash()
        return tx.serialize().hex()

    def test_reject_wrong_dilithium_sig_size(self):
        """PQC witness with correct Dilithium PK size but wrong sig size
        should be rejected."""
        self.log.info("Test: reject wrong Dilithium signature size")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        # Correct PK size (1312), wrong sig size (100 instead of 2420)
        fake_pk = b'\x00' * DILITHIUM_PK_SIZE
        fake_sig = b'\x00' * 100  # Wrong size

        tx_hex = self._create_spending_tx(node, utxo, fake_sig, fake_pk)

        # Should be rejected - sizes don't match any supported PQC algorithm
        assert_raises_rpc_error(
            -26, "PQC public key or signature size mismatch",
            node.sendrawtransaction, tx_hex,
        )
        self.log.info("  -> Correctly rejected wrong Dilithium sig size")

    def test_reject_wrong_sphincs_sig_size(self):
        """PQC witness with correct SPHINCS+ PK size but wrong sig size
        should be rejected."""
        self.log.info("Test: reject wrong SPHINCS+ signature size")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        # Correct PK size (32), wrong sig size (100 instead of 17088)
        fake_pk = b'\x00' * SPHINCS_PK_SIZE
        fake_sig = b'\x00' * 100  # Wrong size

        tx_hex = self._create_spending_tx(node, utxo, fake_sig, fake_pk)

        assert_raises_rpc_error(
            -26, "PQC public key or signature size mismatch",
            node.sendrawtransaction, tx_hex,
        )
        self.log.info("  -> Correctly rejected wrong SPHINCS+ sig size")

    def test_reject_unsupported_pqc_sizes(self):
        """PQC witness with sizes matching no supported algorithm should be
        rejected with key-size-mismatch error."""
        self.log.info("Test: reject unsupported PQC algorithm sizes")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        # Sizes that don't match either Dilithium or SPHINCS+
        fake_pk = b'\x00' * 256   # Not 1312 or 32
        fake_sig = b'\x00' * 512  # Not 2420 or 17088

        tx_hex = self._create_spending_tx(node, utxo, fake_sig, fake_pk)

        assert_raises_rpc_error(
            -26, "PQC public key or signature size mismatch",
            node.sendrawtransaction, tx_hex,
        )
        self.log.info("  -> Correctly rejected unsupported PQC sizes")

    def test_reject_invalid_dilithium_signature(self):
        """PQC witness with correct Dilithium sizes but invalid (all-zero)
        signature should be rejected at verification time."""
        self.log.info("Test: reject invalid Dilithium signature (correct sizes)")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        # Correct sizes but garbage data
        fake_pk = b'\x42' * DILITHIUM_PK_SIZE
        fake_sig = b'\x42' * DILITHIUM_SIG_SIZE

        tx_hex = self._create_spending_tx(node, utxo, fake_sig, fake_pk)

        # Should be rejected - signature verification will fail
        assert_raises_rpc_error(
            -26, "Post-quantum signature verification failed",
            node.sendrawtransaction, tx_hex,
        )
        self.log.info("  -> Correctly rejected invalid Dilithium signature")

    def test_reject_invalid_sphincs_signature(self):
        """PQC witness with correct SPHINCS+ sizes but invalid (all-zero)
        signature should be rejected at verification time."""
        self.log.info("Test: reject invalid SPHINCS+ signature (correct sizes)")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        # Correct sizes but garbage data
        fake_pk = b'\x42' * SPHINCS_PK_SIZE
        fake_sig = b'\x42' * SPHINCS_SIG_SIZE

        tx_hex = self._create_spending_tx(node, utxo, fake_sig, fake_pk)

        assert_raises_rpc_error(
            -26, "Post-quantum signature verification failed",
            node.sendrawtransaction, tx_hex,
        )
        self.log.info("  -> Correctly rejected invalid SPHINCS+ signature")

    def test_standard_p2wpkh_still_works(self):
        """Ensure standard 2-element P2WPKH witness (no PQC) still works."""
        self.log.info("Test: standard P2WPKH (no PQC) still accepted")
        node = self.nodes[0]
        utxo, _ = self._fund_and_get_utxo(node)

        dest = node.getnewaddress("", "bech32")
        amount = Decimal(str(utxo["amount"])) - Decimal("0.001")
        raw_tx = node.createrawtransaction(
            [{"txid": utxo["txid"], "vout": utxo["vout"]}],
            {dest: str(amount)},
        )
        signed = node.signrawtransactionwithwallet(raw_tx)
        assert signed["complete"]

        # Standard ECDSA-only witness should be accepted
        txid = node.sendrawtransaction(signed["hex"])
        assert txid, "Standard P2WPKH transaction was not accepted"
        self.log.info("  -> Standard P2WPKH transaction accepted")

    def run_test(self):
        self.test_standard_p2wpkh_still_works()
        self.test_reject_wrong_dilithium_sig_size()
        self.test_reject_wrong_sphincs_sig_size()
        self.test_reject_unsupported_pqc_sizes()
        self.test_reject_invalid_dilithium_signature()
        self.test_reject_invalid_sphincs_signature()


if __name__ == '__main__':
    PQCWitnessTest(__file__).main()
