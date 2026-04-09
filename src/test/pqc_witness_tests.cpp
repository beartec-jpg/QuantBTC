// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

//! Unit tests for PQC witness verification in the script interpreter.
//! Tests correct ECDSA + wrong Dilithium, wrong sizes, etc.

#include <boost/test/unit_test.hpp>

#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/sphincs.h>
#include <key.h>
#include <pubkey.h>
#include <script/interpreter.h>
#include <script/script.h>
#include <script/sign.h>
#include <script/signingprovider.h>
#include <test/util/transaction_utils.h>

static const unsigned int PQC_WITNESS_FLAGS =
    SCRIPT_VERIFY_P2SH | SCRIPT_VERIFY_WITNESS | SCRIPT_VERIFY_CLEANSTACK;

/// Helper: build a P2WPKH credit + spend pair with a 4-element witness,
/// where the caller controls the PQC sig / pk bytes.
static void BuildPQCSpend(const CKey& key,
                          const std::vector<unsigned char>& pqc_sig,
                          const std::vector<unsigned char>& pqc_pk,
                          CTransactionRef& txCredit_out,
                          CMutableTransaction& txSpend_out)
{
    CPubKey pubkey = key.GetPubKey();
    CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));
    CAmount value = 100000;

    CMutableTransaction credit = BuildCreditingTransaction(spk, value);
    txCredit_out = MakeTransactionRef(credit);

    // Build spending tx stub (no witness yet)
    CScriptWitness dummy_witness;
    txSpend_out = BuildSpendingTransaction(CScript(), dummy_witness, *txCredit_out);

    // Sign ECDSA using the real signing infrastructure
    FlatSigningProvider provider;
    provider.pubkeys[pubkey.GetID()] = pubkey;
    provider.keys[pubkey.GetID()] = key;

    CScript witnessscript;
    witnessscript << OP_DUP << OP_HASH160 << ToByteVector(pubkey.GetID())
                  << OP_EQUALVERIFY << OP_CHECKSIG;

    MutableTransactionSignatureCreator creator(txSpend_out, 0, value, SIGHASH_ALL);
    std::vector<unsigned char> ecdsa_sig;
    BOOST_REQUIRE(creator.CreateSig(provider, ecdsa_sig, pubkey.GetID(),
                                     witnessscript, SigVersion::WITNESS_V0));

    // Build the 4-element witness: [ecdsa_sig, pubkey, pqc_sig, pqc_pk]
    txSpend_out.vin[0].scriptWitness.stack.clear();
    txSpend_out.vin[0].scriptWitness.stack.push_back(ecdsa_sig);
    txSpend_out.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(pubkey.begin(), pubkey.end()));
    txSpend_out.vin[0].scriptWitness.stack.push_back(pqc_sig);
    txSpend_out.vin[0].scriptWitness.stack.push_back(pqc_pk);
}

BOOST_AUTO_TEST_SUITE(pqc_witness_tests)

/// Correct ECDSA sig + correct Dilithium sig → OK
BOOST_AUTO_TEST_CASE(valid_pqc_witness)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();
    CPubKey pubkey = key.GetPubKey();
    CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));
    CAmount value = 100000;

    CMutableTransaction credit_mut = BuildCreditingTransaction(spk, value);
    CTransaction txCredit(credit_mut);
    CMutableTransaction txSpend = BuildSpendingTransaction(CScript(), CScriptWitness(), txCredit);

    // Sign with real ECDSA + real Dilithium
    FlatSigningProvider provider;
    provider.pubkeys[pubkey.GetID()] = pubkey;
    provider.keys[pubkey.GetID()] = key;

    CScript witnessscript;
    witnessscript << OP_DUP << OP_HASH160 << ToByteVector(pubkey.GetID())
                  << OP_EQUALVERIFY << OP_CHECKSIG;

    MutableTransactionSignatureCreator creator(txSpend, 0, value, SIGHASH_ALL);

    // ECDSA sig
    std::vector<unsigned char> ecdsa_sig;
    BOOST_REQUIRE(creator.CreateSig(provider, ecdsa_sig, pubkey.GetID(),
                                     witnessscript, SigVersion::WITNESS_V0));

    // Generate Dilithium keypair and sign the same sighash
    pqc::Dilithium dil;
    std::vector<uint8_t> dil_pk, dil_sk;
    BOOST_REQUIRE(dil.GenerateKeyPair(dil_pk, dil_sk));

    uint256 sighash = SignatureHash(witnessscript, txSpend, 0, SIGHASH_ALL, value, SigVersion::WITNESS_V0);
    std::vector<uint8_t> msg(sighash.begin(), sighash.end());
    std::vector<uint8_t> dil_sig;
    BOOST_REQUIRE(dil.Sign(msg, dil_sk, dil_sig));

    // Build 4-element witness
    txSpend.vin[0].scriptWitness.stack.clear();
    txSpend.vin[0].scriptWitness.stack.push_back(ecdsa_sig);
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(pubkey.begin(), pubkey.end()));
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(dil_sig.begin(), dil_sig.end()));
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(dil_pk.begin(), dil_pk.end()));

    ScriptError err;
    CTransaction tx(txSpend);
    BOOST_CHECK_MESSAGE(
        VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                     PQC_WITNESS_FLAGS,
                     TransactionSignatureChecker(&tx, 0, value, MissingDataBehavior::ASSERT_FAIL),
                     &err),
        "Valid PQC witness should pass verification");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_OK);
}

/// Correct ECDSA sig + wrong Dilithium sig → SCRIPT_ERR_PQC_SIG
BOOST_AUTO_TEST_CASE(valid_sphincs_witness)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();
    CPubKey pubkey = key.GetPubKey();
    CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));
    CAmount value = 100000;

    CMutableTransaction credit_mut = BuildCreditingTransaction(spk, value);
    CTransaction txCredit(credit_mut);
    CMutableTransaction txSpend = BuildSpendingTransaction(CScript(), CScriptWitness(), txCredit);

    FlatSigningProvider provider;
    provider.pubkeys[pubkey.GetID()] = pubkey;
    provider.keys[pubkey.GetID()] = key;

    CScript witnessscript;
    witnessscript << OP_DUP << OP_HASH160 << ToByteVector(pubkey.GetID())
                  << OP_EQUALVERIFY << OP_CHECKSIG;

    MutableTransactionSignatureCreator creator(txSpend, 0, value, SIGHASH_ALL);

    std::vector<unsigned char> ecdsa_sig;
    BOOST_REQUIRE(creator.CreateSig(provider, ecdsa_sig, pubkey.GetID(),
                                     witnessscript, SigVersion::WITNESS_V0));

    pqc::SPHINCS sphincs;
    std::vector<uint8_t> sphincs_pk, sphincs_sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(sphincs_pk, sphincs_sk));

    uint256 sighash = SignatureHash(witnessscript, txSpend, 0, SIGHASH_ALL, value, SigVersion::WITNESS_V0);
    std::vector<uint8_t> msg(sighash.begin(), sighash.end());
    std::vector<uint8_t> sphincs_sig;
    BOOST_REQUIRE(sphincs.Sign(msg, sphincs_sk, sphincs_sig));

    txSpend.vin[0].scriptWitness.stack.clear();
    txSpend.vin[0].scriptWitness.stack.push_back(ecdsa_sig);
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(pubkey.begin(), pubkey.end()));
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(sphincs_sig.begin(), sphincs_sig.end()));
    txSpend.vin[0].scriptWitness.stack.push_back(
        std::vector<unsigned char>(sphincs_pk.begin(), sphincs_pk.end()));

    ScriptError err;
    CTransaction tx(txSpend);
    BOOST_CHECK_MESSAGE(
        VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                     PQC_WITNESS_FLAGS,
                     TransactionSignatureChecker(&tx, 0, value, MissingDataBehavior::ASSERT_FAIL),
                     &err),
        "Valid SPHINCS+ PQC witness should pass verification");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_OK);
}

BOOST_AUTO_TEST_CASE(wrong_dilithium_sig_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    // Generate a valid Dilithium keypair but sign a wrong message
    pqc::Dilithium dil;
    std::vector<uint8_t> dil_pk, dil_sk;
    BOOST_REQUIRE(dil.GenerateKeyPair(dil_pk, dil_sk));

    // Sign a dummy message (NOT the real sighash) → wrong sig
    std::vector<uint8_t> wrong_msg(32, 0xAB);
    std::vector<uint8_t> wrong_sig;
    BOOST_REQUIRE(dil.Sign(wrong_msg, dil_sk, wrong_sig));

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, wrong_sig, dil_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong Dilithium sig should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG);
}

/// Correct ECDSA sig + wrong-size Dilithium sig → SCRIPT_ERR_PQC_SIG_SIZE
BOOST_AUTO_TEST_CASE(wrong_size_dilithium_sig_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    // Sig that's too short (100 bytes instead of 2420)
    std::vector<unsigned char> short_sig(100, 0x42);
    std::vector<unsigned char> valid_pk(pqc::Dilithium::PUBLIC_KEY_SIZE, 0x00);

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, short_sig, valid_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong-size Dilithium sig should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG_SIZE);
}

/// Correct ECDSA sig + wrong-size Dilithium pubkey → SCRIPT_ERR_PQC_SIG_SIZE
BOOST_AUTO_TEST_CASE(wrong_size_dilithium_pk_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    std::vector<unsigned char> valid_sig(pqc::Dilithium::SIGNATURE_SIZE, 0x00);
    // Pubkey that's too short (64 bytes instead of 1312)
    std::vector<unsigned char> short_pk(64, 0x42);

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, valid_sig, short_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong-size Dilithium pubkey should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG_SIZE);
}

/// Correct ECDSA sig + correct-size but wrong-content SPHINCS+ sig → SCRIPT_ERR_PQC_SIG
BOOST_AUTO_TEST_CASE(wrong_sphincs_sig_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    // Generate a real SPHINCS+ keypair but sign a wrong message
    pqc::SPHINCS sphincs;
    std::vector<uint8_t> sphincs_pk, sphincs_sk;
    BOOST_REQUIRE(sphincs.GenerateKeyPair(sphincs_pk, sphincs_sk));

    // Sign a dummy message (NOT the real sighash) → wrong sig
    std::vector<uint8_t> wrong_msg(32, 0xAB);
    std::vector<uint8_t> wrong_sig;
    BOOST_REQUIRE(sphincs.Sign(wrong_msg, sphincs_sk, wrong_sig));

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, wrong_sig, sphincs_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong SPHINCS+ sig should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG);
}

/// Correct ECDSA sig + wrong-size SPHINCS+ sig → SCRIPT_ERR_PQC_SIG_SIZE
BOOST_AUTO_TEST_CASE(wrong_size_sphincs_sig_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    // Sig that's too short (100 bytes instead of 17088)
    std::vector<unsigned char> short_sig(100, 0x42);
    std::vector<unsigned char> valid_pk(pqc::SPHINCS::PUBLIC_KEY_SIZE, 0x00);

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, short_sig, valid_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong-size SPHINCS+ sig should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG_SIZE);
}

/// Correct ECDSA sig + correct-size SPHINCS+ sig + wrong-size SPHINCS+ pubkey → SCRIPT_ERR_PQC_SIG_SIZE
BOOST_AUTO_TEST_CASE(wrong_size_sphincs_pk_rejected)
{
    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();

    std::vector<unsigned char> valid_sig(pqc::SPHINCS::SIGNATURE_SIZE, 0x00);
    // Pubkey that's too large (64 bytes instead of 32)
    std::vector<unsigned char> wrong_pk(64, 0x42);

    CTransactionRef txCredit;
    CMutableTransaction txSpend;
    BuildPQCSpend(key, valid_sig, wrong_pk, txCredit, txSpend);

    ScriptError err;
    CTransaction tx(txSpend);
    CScript spk = txCredit->vout[0].scriptPubKey;
    BOOST_CHECK_MESSAGE(
        !VerifyScript(CScript(), spk, &txSpend.vin[0].scriptWitness,
                      PQC_WITNESS_FLAGS,
                      TransactionSignatureChecker(&tx, 0, txCredit->vout[0].nValue, MissingDataBehavior::ASSERT_FAIL),
                      &err),
        "Wrong-size SPHINCS+ pubkey should be rejected");
    BOOST_CHECK_EQUAL(err, SCRIPT_ERR_PQC_SIG_SIZE);
}

BOOST_AUTO_TEST_SUITE_END()
