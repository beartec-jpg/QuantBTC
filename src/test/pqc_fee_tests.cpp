// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <crypto/pqc/dilithium.h>
#include <crypto/pqc/pqc_config.h>
#include <key.h>
#include <script/descriptor.h>
#include <script/sign.h>
#include <script/signingprovider.h>

BOOST_AUTO_TEST_SUITE(pqc_fee_tests)

/// When PQC hybrid signatures are enabled, WPKHDescriptor must report
/// a MaxSatSize that accounts for the Dilithium sig + pubkey, and
/// MaxSatisfactionElems must return 4 (not 2).
BOOST_AUTO_TEST_CASE(wpkh_maxsatsize_pqc)
{
    auto& cfg = pqc::PQCConfig::GetInstance();
    const bool orig_hybrid = cfg.enable_hybrid_signatures;

    // --- PQC disabled: classic P2WPKH sizes ---
    cfg.enable_hybrid_signatures = false;
    {
        ECC_Context ecc_context{};
        CKey key = GenerateRandomKey();
        CPubKey pubkey = key.GetPubKey();

        FlatSigningProvider provider;
        provider.pubkeys[pubkey.GetID()] = pubkey;

        CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));
        auto desc = InferDescriptor(spk, provider);
        BOOST_REQUIRE(desc);

        auto sat_weight = desc->MaxSatisfactionWeight(true);
        auto sat_elems = desc->MaxSatisfactionElems();
        BOOST_REQUIRE(sat_weight.has_value());
        BOOST_REQUIRE(sat_elems.has_value());

        // Classic P2WPKH: 1 + 72 + 1 + 33 = 107
        BOOST_CHECK_EQUAL(*sat_weight, 107);
        BOOST_CHECK_EQUAL(*sat_elems, 2);
    }

    // --- PQC enabled: must include Dilithium overhead ---
    cfg.enable_hybrid_signatures = true;
    {
        ECC_Context ecc_context{};
        CKey key = GenerateRandomKey();
        CPubKey pubkey = key.GetPubKey();

        FlatSigningProvider provider;
        provider.pubkeys[pubkey.GetID()] = pubkey;

        CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));
        auto desc = InferDescriptor(spk, provider);
        BOOST_REQUIRE(desc);

        auto sat_weight = desc->MaxSatisfactionWeight(true);
        auto sat_elems = desc->MaxSatisfactionElems();
        BOOST_REQUIRE(sat_weight.has_value());
        BOOST_REQUIRE(sat_elems.has_value());

        // PQC P2WPKH: 107 + 3 + 2420 + 3 + 1312 = 3845
        const int64_t expected = 107 + 3 + pqc::Dilithium::SIGNATURE_SIZE + 3 + pqc::Dilithium::PUBLIC_KEY_SIZE;
        BOOST_CHECK_EQUAL(*sat_weight, expected);
        BOOST_CHECK_EQUAL(*sat_elems, 4);
        // vsize must be ≥ 1000 vB — the whole point of the fix
        BOOST_CHECK_GE(*sat_weight, 1000);
    }

    // Restore original setting
    cfg.enable_hybrid_signatures = orig_hybrid;
}

/// DummySignatureCreator must produce a 4-element witness stack
/// when PQC hybrid signatures are enabled.
BOOST_AUTO_TEST_CASE(dummy_signature_creator_pqc)
{
    auto& cfg = pqc::PQCConfig::GetInstance();
    const bool orig_hybrid = cfg.enable_hybrid_signatures;

    ECC_Context ecc_context{};
    CKey key = GenerateRandomKey();
    CPubKey pubkey = key.GetPubKey();

    FlatSigningProvider provider;
    provider.pubkeys[pubkey.GetID()] = pubkey;
    provider.keys[pubkey.GetID()] = key;

    CScript spk = GetScriptForDestination(WitnessV0KeyHash(pubkey));

    // --- PQC disabled: 2-element witness ---
    cfg.enable_hybrid_signatures = false;
    {
        SignatureData sigdata;
        bool ok = ProduceSignature(provider, DUMMY_MAXIMUM_SIGNATURE_CREATOR, spk, sigdata);
        BOOST_CHECK(ok);
        BOOST_CHECK_EQUAL(sigdata.scriptWitness.stack.size(), 2U);
    }

    // --- PQC enabled: 4-element witness ---
    cfg.enable_hybrid_signatures = true;
    {
        SignatureData sigdata;
        // ProduceSignature may return false (dummy sigs don't pass VerifyScript)
        // but the witness structure is what matters for size estimation.
        (void)ProduceSignature(provider, DUMMY_MAXIMUM_SIGNATURE_CREATOR, spk, sigdata);
        BOOST_CHECK_EQUAL(sigdata.scriptWitness.stack.size(), 4U);
        // Element 2 = dummy Dilithium sig (2420 bytes)
        BOOST_CHECK_EQUAL(sigdata.scriptWitness.stack[2].size(), pqc::Dilithium::SIGNATURE_SIZE);
        // Element 3 = dummy Dilithium pubkey (1312 bytes)
        BOOST_CHECK_EQUAL(sigdata.scriptWitness.stack[3].size(), pqc::Dilithium::PUBLIC_KEY_SIZE);
    }

    cfg.enable_hybrid_signatures = orig_hybrid;
}

BOOST_AUTO_TEST_SUITE_END()
