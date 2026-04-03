// Copyright (c) 2024 The QuantumBTC developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

//! Fuzz target for the PQC witness dispatch in interpreter.cpp.
//! Generates random 4-element witness stacks with sizes around the
//! Dilithium boundaries (2420/1312) and feeds them through VerifyScript
//! against a P2WPKH scriptPubKey.

#include <crypto/pqc/dilithium.h>
#include <key.h>
#include <pubkey.h>
#include <script/interpreter.h>
#include <script/script.h>
#include <test/fuzz/FuzzedDataProvider.h>
#include <test/fuzz/fuzz.h>
#include <test/fuzz/util.h>
#include <test/util/transaction_utils.h>

static CKey s_key;
static CPubKey s_pubkey;
static CScript s_spk;

void initialize_pqc_witness()
{
    static ECC_Context ecc_context{};
    s_key = GenerateRandomKey();
    s_pubkey = s_key.GetPubKey();
    s_spk = GetScriptForDestination(WitnessV0KeyHash(s_pubkey));
}

FUZZ_TARGET(pqc_witness, .init = initialize_pqc_witness)
{
    FuzzedDataProvider fdp(buffer.data(), buffer.size());

    // Build a crediting tx for our fixed P2WPKH key
    const CAmount value = 100000;
    CMutableTransaction credit = BuildCreditingTransaction(s_spk, value);
    CTransaction txCredit(credit);
    CMutableTransaction txSpend = BuildSpendingTransaction(CScript(), CScriptWitness(), txCredit);

    // Decide witness stack size: focus on 4 elements (the PQC path)
    // but also test 2, 3, 5 to exercise boundary conditions
    const uint8_t stack_len = fdp.PickValueInArray<uint8_t>({2, 3, 4, 4, 4, 4, 5});

    CScriptWitness witness;
    for (uint8_t i = 0; i < stack_len; i++) {
        size_t elem_size;
        if (stack_len == 4 && i == 2) {
            // PQC sig position: vary around 2420
            elem_size = fdp.PickValueInArray<size_t>({
                0, 1, 100, 2419, 2420, 2421, 4840, 17088});
        } else if (stack_len == 4 && i == 3) {
            // PQC pk position: vary around 1312
            elem_size = fdp.PickValueInArray<size_t>({
                0, 1, 32, 33, 64, 1311, 1312, 1313, 2624});
        } else {
            // ECDSA sig or pubkey position
            elem_size = fdp.ConsumeIntegralInRange<size_t>(0, 200);
        }
        witness.stack.push_back(
            ConsumeFixedLengthByteVector(fdp, elem_size));
    }

    txSpend.vin[0].scriptWitness = witness;

    ScriptError err;
    CTransaction tx(txSpend);
    // Must not crash regardless of witness contents
    (void)VerifyScript(
        CScript(), s_spk, &witness,
        SCRIPT_VERIFY_P2SH | SCRIPT_VERIFY_WITNESS,
        TransactionSignatureChecker(&tx, 0, value, MissingDataBehavior::FAIL),
        &err);
}
