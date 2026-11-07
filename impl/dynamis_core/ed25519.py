"""ed25519 — pure-python RFC 8032, stdlib only (ADR-0007).

The witness band needed real signatures; the reference runs anywhere the
fleet runs, with zero dependency risk, so the curve is implemented here
rather than imported. Auditable reference code, not a fast one: each point
operation is ~10 modular multiplications, a scalar mult ~5ms in CPython —
a seal (7 signatures) and an audit (~30 verifications) stay well under a
second. It is NOT constant-time, and that is named, not hidden: in
production the band's keys live in independent witnesses' HSMs; in the kit
the band is in-process. Correctness is pinned to RFC 8032 §7.1 test
vectors (TEST_VECTORS) — executable below.
"""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
_I = pow(2, (P - 1) // 4, P)


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * _I) % P
    if x % 2 != 0:
        x = P - x
    return x


_By = 4 * _inv(5) % P
_Bx = _xrecover(_By)
B = (_Bx % P, _By % P, 1, _Bx * _By % P)      # extended coordinates
IDENT = (0, 1, 1, 0)


def _add(Pt, Qt):
    (x1, y1, z1, t1), (x2, y2, z2, t2) = Pt, Qt
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = t1 * 2 * D * t2 % P
    dd = z1 * 2 * z2 % P
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _mult(Pt, n: int):
    Qt = IDENT
    while n:
        if n & 1:
            Qt = _add(Qt, Pt)
        Pt = _add(Pt, Pt)
        n >>= 1
    return Qt


def _compress(Pt) -> bytes:
    x, y, z, _ = Pt
    zi = _inv(z)
    x = x * zi % P
    y = y * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= P:
        raise ValueError("point not on curve")
    x = _xrecover(y)
    if x & 1 != sign:
        x = P - x
    return (x, y, 1, x * y % P)


def _clamp(h: bytes) -> int:
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a


def publickey(seed: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    return _compress(_mult(B, _clamp(h)))


def sign(msg: bytes, seed: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = _clamp(h)
    A = _compress(_mult(B, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + msg).digest(), "little") % L
    R = _compress(_mult(B, r))
    k = int.from_bytes(hashlib.sha512(R + A + msg).digest(), "little") % L
    s = (r + k * a) % L
    return R + s.to_bytes(32, "little")


def verify(msg: bytes, sig: bytes, pub: bytes) -> bool:
    if len(sig) != 64 or len(pub) != 32:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= L:
        return False
    try:
        A = _decompress(pub)
        R = _decompress(sig[:32])
    except ValueError:
        return False
    k = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % L
    left = _mult(B, s)
    right = _add(R, _mult(A, k))
    (x1, y1, z1, _), (x2, y2, z2, _) = left, right
    return (x1 * z2 - x2 * z1) % P == 0 and (y1 * z2 - y2 * z1) % P == 0


# RFC 8032 §7.1, test vectors 1-3: (seed, public key, message, signature)
TEST_VECTORS = (
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
)


def self_test() -> dict:
    """Pin the module to the RFC vectors: pubkey derivation, signature
    bytes, verification, and a tampered-byte rejection, per vector."""
    out = {"vectors": 0, "pubkeys_ok": 0, "signatures_ok": 0, "tamper_rejected": 0}
    for seed_hex, pub_hex, msg_hex, sig_hex in TEST_VECTORS:
        seed, msg = bytes.fromhex(seed_hex), bytes.fromhex(msg_hex)
        pub, sig = bytes.fromhex(pub_hex), bytes.fromhex(sig_hex)
        out["vectors"] += 1
        out["pubkeys_ok"] += publickey(seed) == pub
        out["signatures_ok"] += sign(msg, seed) == sig
        bad = bytearray(sig)
        bad[0] ^= 1
        out["tamper_rejected"] += not verify(msg, bytes(bad), pub)
    out["ok"] = all(v == out["vectors"] for k, v in out.items() if k != "ok")
    return out
