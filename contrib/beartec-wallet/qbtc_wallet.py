#!/usr/bin/env python3
"""
QuantumBTC (QBTC) wallet integration library for BearTec Wallet.

Supports:
  - PQC + ECDSA keypair generation from a BIP-32 seed
  - qbtct1... Bech32 address creation
  - Hybrid PQC transaction signing (ECDSA + Dilithium witness)
  - RPC broadcast to qbtctestnet node
  - 2-of-3 Shamir secret sharing compatible key splitting

Witness structure (P2WPKH-PQC hybrid):
  [0] ECDSA DER signature          (~71 bytes)
  [1] Compressed ECDSA public key   (33 bytes)
  [2] Dilithium signature           (2420 bytes)
  [3] Dilithium public key          (1312 bytes)

WARNING: The Dilithium implementation in this file is INCOMPATIBLE with the
node as of the ML-DSA-44 upgrade.  The C++ node (dilithium.cpp) now uses the
real CRYSTALS-Dilithium2 / NIST ML-DSA-44 lattice-based reference
implementation.  The old HMAC-SHA512-based stub has been removed.

To sign Dilithium witnesses from Python you must use a binding to the real
algorithm, for example:
  - liboqs-python (https://github.com/open-quantum-safe/liboqs-python)
      import oqs
      with oqs.Signature("Dilithium2") as signer:
          pk = signer.generate_keypair()
          sig = signer.sign(message)
  - pqcrypto (https://github.com/nicowillis/pqcrypto)

Until a Python binding is integrated, the DilithiumKey class below is
DISABLED and will raise NotImplementedError if called.  The wallet can
still broadcast ECDSA-only transactions to the node.
"""

import hashlib
import hmac
import struct
import json
import secrets
import urllib.request
import base64
from typing import Tuple, Optional, List

# ---------------------------------------------------------------------------
# Constants (sizes match the real NIST ML-DSA-44 / CRYSTALS-Dilithium2 spec)
# ---------------------------------------------------------------------------
DILITHIUM_PK_SIZE = 1312
DILITHIUM_SK_SIZE = 2560  # Updated: 2*SEEDBYTES + TRBYTES + poly vectors
DILITHIUM_SIG_SIZE = 2420

# Bech32 parameters for qbtctestnet
QBTC_TESTNET_HRP = "qbtct"
QBTC_MAINNET_HRP = "qbtc"

# RPC defaults
DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 28332


# ---------------------------------------------------------------------------
# Bech32 encoding (BIP-173)
# ---------------------------------------------------------------------------
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values):
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp, data):
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp, witver, witprog):
    """Encode a segwit address."""
    data = [witver] + _convertbits(witprog, 8, 5)
    checksum = _bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in data + checksum)


def _convertbits(data, frombits, tobits, pad=True):
    acc, bits, ret = 0, 0, []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


# ---------------------------------------------------------------------------
# HMAC-SHA512 helpers (matching the C++ node exactly)
# ---------------------------------------------------------------------------
def hmac_sha512(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha512).digest()


def expand_to_size(seed: bytes, context: bytes, outlen: int) -> bytes:
    """Counter-mode HMAC-SHA512 expansion (matches C++ expand_to_size)."""
    result = b""
    counter = 0
    while len(result) < outlen:
        block_data = context + struct.pack("<I", counter)
        block = hmac_sha512(seed, block_data)
        result += block
        counter += 1
    return result[:outlen]


# ---------------------------------------------------------------------------
# Dilithium key management
#
# NOTE: The HMAC-SHA512 stub has been removed.  The node now uses the real
# CRYSTALS-Dilithium2 / NIST ML-DSA-44 reference implementation.
# This class raises NotImplementedError until a Python binding (e.g.
# liboqs-python) is integrated.
# ---------------------------------------------------------------------------
class DilithiumKey:
    """CRYSTALS-Dilithium2 (ML-DSA-44) key stub.

    IMPORTANT: The previous HMAC-SHA512 implementation was NOT real lattice
    cryptography and has been removed from the node.  Signatures produced by
    the old code will NOT verify against the new node.

    To use Dilithium signing from Python, install liboqs-python:
        pip install liboqs-python
    and use:
        import oqs
        with oqs.Signature("Dilithium2") as signer:
            pk = signer.generate_keypair()
            sig = signer.sign(message)
            ok  = signer.verify(message, sig, pk)
    """

    def __init__(self):
        raise NotImplementedError(
            "The HMAC-SHA512 Dilithium stub has been removed. "
            "Install liboqs-python and use oqs.Signature('Dilithium2') instead."
        )

    @classmethod
    def from_ecdsa_privkey(cls, ecdsa_privkey: bytes) -> "DilithiumKey":
        raise NotImplementedError(
            "The HMAC-SHA512 Dilithium stub has been removed. "
            "Use liboqs-python (oqs.Signature('Dilithium2')) for real ML-DSA-44."
        )

    @classmethod
    def from_seed(cls, seed: bytes) -> "DilithiumKey":
        raise NotImplementedError(
            "The HMAC-SHA512 Dilithium stub has been removed. "
            "Use liboqs-python (oqs.Signature('Dilithium2')) for real ML-DSA-44."
        )


# ---------------------------------------------------------------------------
# ECDSA key (uses Python ecdsa library if available, else stubs for RPC-only use)
# ---------------------------------------------------------------------------
try:
    import ecdsa
    from ecdsa.util import sigencode_der_canonize, sigdecode_der

    class ECDSAKey:
        """secp256k1 ECDSA key for signing Bitcoin transactions."""

        def __init__(self, privkey_bytes: Optional[bytes] = None):
            if privkey_bytes:
                self._sk = ecdsa.SigningKey.from_string(privkey_bytes, curve=ecdsa.SECP256k1)
            else:
                self._sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
            self._vk = self._sk.get_verifying_key()

        @property
        def privkey(self) -> bytes:
            return self._sk.to_string()

        @property
        def pubkey_compressed(self) -> bytes:
            """33-byte compressed public key."""
            point = self._vk.pubkey.point
            prefix = b"\x02" if point.y() % 2 == 0 else b"\x03"
            return prefix + point.x().to_bytes(32, "big")

        def sign(self, sighash: bytes) -> bytes:
            """DER-encoded ECDSA signature."""
            return self._sk.sign_digest(sighash, sigencode=sigencode_der_canonize)

        def pubkey_hash160(self) -> bytes:
            """HASH160(compressed_pubkey) for P2WPKH."""
            sha = hashlib.sha256(self.pubkey_compressed).digest()
            return hashlib.new("ripemd160", sha).digest()

    ECDSA_AVAILABLE = True
except ImportError:
    ECDSA_AVAILABLE = False

    class ECDSAKey:
        """Stub - install 'ecdsa' package for offline signing."""
        def __init__(self, privkey_bytes=None):
            raise ImportError("Install 'ecdsa' package: pip install ecdsa")


# ---------------------------------------------------------------------------
# QBTC Hybrid Keypair
# ---------------------------------------------------------------------------
class QBTCKeyPair:
    """Combined ECDSA + Dilithium keypair for QuantumBTC."""

    def __init__(self, ecdsa_key: ECDSAKey):
        self.ecdsa = ecdsa_key
        self.dilithium = DilithiumKey.from_ecdsa_privkey(ecdsa_key.privkey)

    @classmethod
    def generate(cls) -> "QBTCKeyPair":
        """Generate a new random hybrid keypair."""
        return cls(ECDSAKey())

    @classmethod
    def from_seed(cls, seed: bytes, path_index: int = 0) -> "QBTCKeyPair":
        """Derive from a BIP-32-style master seed (same seed used for BTC/ETH/etc).
        
        Derivation:
            child_key = HMAC-SHA512(seed, "QBTC" || path_index_be32)[0:32]
        
        This is compatible with your existing 2-of-3 key splitting since
        the same master seed produces the same child key deterministically.
        """
        idx_bytes = struct.pack(">I", path_index)
        child = hmac_sha512(seed, b"QBTC" + idx_bytes)
        ecdsa = ECDSAKey(child[:32])
        return cls(ecdsa)

    @classmethod
    def from_privkey_hex(cls, hex_privkey: str) -> "QBTCKeyPair":
        """Import from a hex-encoded 32-byte ECDSA private key."""
        return cls(ECDSAKey(bytes.fromhex(hex_privkey)))

    def address(self, hrp: str = QBTC_TESTNET_HRP) -> str:
        """Generate qbtct1... Bech32 P2WPKH address."""
        return bech32_encode(hrp, 0, list(self.ecdsa.pubkey_hash160()))

    def export_keys(self) -> dict:
        """Export all key material (handle securely!)."""
        return {
            "ecdsa_privkey": self.ecdsa.privkey.hex(),
            "ecdsa_pubkey": self.ecdsa.pubkey_compressed.hex(),
            "dilithium_pubkey": self.dilithium.public_key.hex(),
            "dilithium_privkey_seed": self.dilithium.seed.hex(),
            "address_testnet": self.address(QBTC_TESTNET_HRP),
            "address_mainnet": self.address(QBTC_MAINNET_HRP),
        }


# ---------------------------------------------------------------------------
# 2-of-3 Shamir Secret Sharing (works over GF(256))
# ---------------------------------------------------------------------------
class ShamirSplit:
    """2-of-3 Shamir secret sharing for hybrid PQC keys.
    
    Splits the 32-byte ECDSA private key into 3 shares where any 2
    can reconstruct it. The Dilithium key is derived deterministically
    from the ECDSA key, so splitting the ECDSA key is sufficient.
    """

    @staticmethod
    def _gf256_mul(a: int, b: int) -> int:
        """Multiply in GF(2^8) with irreducible polynomial x^8+x^4+x^3+x+1."""
        p = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            carry = a & 0x80
            a = (a << 1) & 0xff
            if carry:
                a ^= 0x1b
            b >>= 1
        return p

    @staticmethod
    def _gf256_inv(a: int) -> int:
        """Multiplicative inverse in GF(256) via a^254 = a^(-1)."""
        if a == 0:
            return 0
        # Compute a^254 by repeated squaring: a^(2^8-2)
        r = a
        for _ in range(6):
            r = ShamirSplit._gf256_mul(r, r)
            r = ShamirSplit._gf256_mul(r, a)
        # r = a^127 now, one more square gives a^254
        r = ShamirSplit._gf256_mul(r, r)
        return r

    @staticmethod
    def split_key(secret: bytes) -> Tuple[bytes, bytes, bytes]:
        """Split a secret into 3 shares (threshold=2).
        
        For each byte of the secret:
          f(x) = secret_byte + rand_coeff * x  (in GF(256))
          share_i = f(i+1) for i in {0, 1, 2}
        """
        n = len(secret)
        coeffs = secrets.token_bytes(n)  # random coefficients
        shares = [bytearray(n) for _ in range(3)]
        for i in range(n):
            s = secret[i]
            c = coeffs[i]
            for j in range(3):
                x = j + 1  # evaluation points: 1, 2, 3
                shares[j][i] = s ^ ShamirSplit._gf256_mul(c, x)
        return bytes(shares[0]), bytes(shares[1]), bytes(shares[2])

    @staticmethod
    def recover_key(share_a: bytes, idx_a: int, share_b: bytes, idx_b: int) -> bytes:
        """Recover secret from any 2 shares.
        
        idx_a, idx_b are 1-based share indices (1, 2, or 3).
        """
        assert len(share_a) == len(share_b)
        n = len(share_a)
        xa, xb = idx_a, idx_b
        result = bytearray(n)
        for i in range(n):
            ya, yb = share_a[i], share_b[i]
            # Lagrange interpolation at x=0 in GF(256)
            # L_a(0) = xb / (xb - xa)
            # L_b(0) = xa / (xa - xb)
            denom_a = xa ^ xb  # xb - xa in GF(256) is xb XOR xa
            la = ShamirSplit._gf256_mul(xb, ShamirSplit._gf256_inv(denom_a))
            lb = ShamirSplit._gf256_mul(xa, ShamirSplit._gf256_inv(denom_a))
            result[i] = ShamirSplit._gf256_mul(ya, la) ^ ShamirSplit._gf256_mul(yb, lb)
        return bytes(result)


# ---------------------------------------------------------------------------
# RPC Client
# ---------------------------------------------------------------------------
class QBTCRpc:
    """JSON-RPC client for QuantumBTC testnet node."""

    def __init__(self, host=DEFAULT_RPC_HOST, port=DEFAULT_RPC_PORT,
                 user="", password="", wallet=""):
        self.url = f"http://{host}:{port}"
        if wallet:
            self.url += f"/wallet/{wallet}"
        self.auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._id = 0

    @classmethod
    def from_cookie(cls, cookie_path: str = None, host=DEFAULT_RPC_HOST,
                    port=DEFAULT_RPC_PORT, wallet=""):
        """Create RPC client from .cookie auth file."""
        import os
        if cookie_path is None:
            cookie_path = os.path.expanduser("~/.bitcoin/qbtctestnet/.cookie")
        with open(cookie_path) as f:
            cookie = f.read().strip()
        user, password = cookie.split(":")
        return cls(host, port, user, password, wallet)

    def call(self, method: str, params=None) -> dict:
        """Make a JSON-RPC call. Returns the result or raises on error."""
        self._id += 1
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or []
        }).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {self.auth}",
            },
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        if result.get("error"):
            raise RuntimeError(f"RPC error: {result['error']}")
        return result["result"]

    def getblockchaininfo(self):
        return self.call("getblockchaininfo")

    def sendrawtransaction(self, hex_tx: str) -> str:
        return self.call("sendrawtransaction", [hex_tx])

    def getnewaddress(self) -> str:
        return self.call("getnewaddress")

    def generatetoaddress(self, nblocks: int, address: str):
        return self.call("generatetoaddress", [nblocks, address])

    def getbalance(self):
        return self.call("getbalance")

    def listunspent(self, minconf=1, maxconf=9999999):
        return self.call("listunspent", [minconf, maxconf])

    def getrawtransaction(self, txid: str, verbose=True):
        return self.call("getrawtransaction", [txid, verbose])

    def decoderawtransaction(self, hex_tx: str):
        return self.call("decoderawtransaction", [hex_tx])

    def sendtoaddress(self, address: str, amount: float, fee_rate: int = 10):
        return self.call("sendtoaddress", {
            "address": address,
            "amount": amount,
            "fee_rate": fee_rate,
        })


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def self_test():
    """Run self-test of Dilithium signing + Bech32 address generation."""
    print("=== QBTC Wallet Library Self-Test ===\n")

    # 1. Test Dilithium key derivation and signing
    seed = bytes.fromhex("deadbeef" * 8)  # 32-byte test seed
    dk = DilithiumKey.from_seed(seed)
    assert len(dk.public_key) == DILITHIUM_PK_SIZE
    assert len(dk.private_key) == DILITHIUM_SK_SIZE
    print(f"Dilithium PK: {dk.public_key[:16].hex()}... ({len(dk.public_key)} bytes)")

    msg = hashlib.sha256(b"test message").digest()
    sig = dk.sign(msg)
    assert len(sig) == DILITHIUM_SIG_SIZE
    assert dk.verify(msg, sig), "Signature verification failed!"
    print(f"Dilithium signature: {sig[:16].hex()}... ({len(sig)} bytes) VERIFIED")

    # Determinism check
    sig2 = dk.sign(msg)
    assert sig == sig2, "Signatures not deterministic!"
    print("Determinism: PASS (same key + message = same signature)")

    # Wrong message should fail
    assert not dk.verify(b"wrong", sig), "Should have failed!"
    print("Wrong-message rejection: PASS")

    # 2. Test Bech32 address generation
    if ECDSA_AVAILABLE:
        kp = QBTCKeyPair.from_seed(seed)
        addr = kp.address()
        assert addr.startswith("qbtct1"), f"Bad address prefix: {addr}"
        print(f"\nAddress (testnet): {addr}")
        print(f"Address (mainnet): {kp.address(QBTC_MAINNET_HRP)}")
        print(f"ECDSA pubkey: {kp.ecdsa.pubkey_compressed.hex()}")
        print(f"Dilithium pubkey: {kp.dilithium.public_key[:32].hex()}... ({DILITHIUM_PK_SIZE} bytes)")
    else:
        print("\nSkipping ECDSA tests (install 'ecdsa' package)")

    # 3. Test 2-of-3 Shamir splitting
    secret = secrets.token_bytes(32)
    s1, s2, s3 = ShamirSplit.split_key(secret)
    assert ShamirSplit.recover_key(s1, 1, s2, 2) == secret
    assert ShamirSplit.recover_key(s1, 1, s3, 3) == secret
    assert ShamirSplit.recover_key(s2, 2, s3, 3) == secret
    print(f"\n2-of-3 Shamir split/recover: PASS (all 3 pairs recover correctly)")

    # 4. Demonstrate full hybrid key from split recovery
    if ECDSA_AVAILABLE:
        ecdsa_secret = kp.ecdsa.privkey
        sh1, sh2, sh3 = ShamirSplit.split_key(ecdsa_secret)
        recovered = ShamirSplit.recover_key(sh1, 1, sh3, 3)
        recovered_kp = QBTCKeyPair.from_privkey_hex(recovered.hex())
        assert recovered_kp.address() == kp.address()
        assert recovered_kp.dilithium.public_key == kp.dilithium.public_key
        print(f"Recovered hybrid key matches original: PASS")
        print(f"  Address:        {recovered_kp.address()}")
        print(f"  Dilithium PK:   {recovered_kp.dilithium.public_key[:32].hex()}...")

    print("\n=== All tests passed ===")


if __name__ == "__main__":
    self_test()
