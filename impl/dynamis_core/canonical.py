"""DYNAMIS reference implementation — canonical serialization and integer money.

The µ¢ convention (roshpina/kernel, ADR-0007): every monetary protocol value is an
integer, 1 µ¢ = 10⁻⁶ USDS. Floats are rejected at the wire boundary. Canonical bytes
are the only thing ever signed or hashed.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any

MU_PER_USDS = 1_000_000  # 1 µ¢ = 10⁻⁶ USDS; $1 = 1_000_000 µ¢

# ADR-0007: canonical JSON = sorted keys, tight separators, integers only, UTF-8.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def usds(dollars: int) -> int:
    """The only sanctioned way to write a dollar amount in code: usds(40) = $40 in µ¢.
    Never hand-convert literals — that is how unit bugs are born."""
    if isinstance(dollars, bool) or not isinstance(dollars, int):
        raise ValueError("usds() takes an integer dollar count")
    return dollars * MU_PER_USDS


def _prepare(obj: Any) -> Any:
    """Dataclasses (e.g. Claim inside an event body) become plain dicts recursively."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _prepare(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _prepare(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_prepare(v) for v in obj]
    return obj


def _reject_floats(obj: Any, path: str = "$") -> None:
    if isinstance(obj, float):
        raise ValueError(f"float at {path}: canonical wire is integers-only (ADR-0007)")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise ValueError(f"non-string key at {path}: {k!r}")
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_floats(v, f"{path}[{i}]")


def canon(obj: Any) -> bytes:
    """Canonical JSON bytes. Accepts dataclasses; raises on any float anywhere."""
    prepared = _prepare(obj)
    _reject_floats(prepared)
    return json.dumps(
        prepared, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_hash(obj: Any) -> str:
    """Hash of the canonical form — the hash-chain link of every ledger/receipt."""
    return sha256_hex(canon(obj))


def domain_hash(domain: str, payload: Any) -> str:
    """Domain-separated digest: prevents a signature over one object type being
    replayed as another (job.open vs job.settle vs checkpoint)."""
    if not re.fullmatch(r"[a-z0-9_.]{1,64}", domain):
        raise ValueError(f"bad signature domain: {domain!r}")
    return sha256_hex(canon({"dyn_domain": domain, "payload": payload}))


def check_int_amount(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer (µ¢), got {type(value).__name__}")
    if value < minimum:
        raise ValueError(f"{field} below minimum {minimum}: {value}")
    return value


def check_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"{field} must match {_ID_RE.pattern}, got {value!r}")
    return value


def bps_of(amount: int, bps: int) -> int:
    """Integer basis-points share."""
    if not 0 <= bps <= 10000:
        raise ValueError(f"bps out of range: {bps}")
    return amount * bps // 10000


def split_bps(amount: int, weights: list[int]) -> list[int]:
    """Split `amount` by bps weights; the last share absorbs the rounding remainder
    so the parts always sum exactly to `amount`."""
    if sum(weights) != 10000:
        raise ValueError(f"weights must sum to 10000, got {sum(weights)}")
    parts = [bps_of(amount, w) for w in weights[:-1]]
    parts.append(amount - sum(parts))
    return parts
