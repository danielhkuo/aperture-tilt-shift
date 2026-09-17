"""Transfer curves, so frames are averaged in linear light."""

from __future__ import annotations

import numpy as np

_A, _B, _C = 0.17883277, 0.28466892, 0.55991073  # HLG (BT.2100)


def _decode(v: np.ndarray, transfer: str) -> np.ndarray:
    if transfer == "linear":
        return v
    if transfer == "srgb":
        return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    if transfer == "hlg":
        return np.where(v <= 0.5, v * v / 3, (np.exp((v - _C) / _A) + _B) / 12)
    raise ValueError(f"unknown transfer {transfer!r}")


def _encode(v: np.ndarray, transfer: str) -> np.ndarray:
    if transfer == "linear":
        return v
    if transfer == "srgb":
        return np.where(v <= 0.0031308, v * 12.92, 1.055 * np.maximum(v, 1e-12) ** (1 / 2.4) - 0.055)
    if transfer == "hlg":
        return np.where(v <= 1 / 12, np.sqrt(3 * v), _A * np.log(np.maximum(12 * v - _B, 1e-12)) + _C)
    raise ValueError(f"unknown transfer {transfer!r}")


def to_linear_lut(transfer: str) -> np.ndarray:
    """256-entry float32 table: 8-bit code value → linear light in [0, 1]."""
    return _decode(np.arange(256) / 255.0, transfer).astype(np.float32)


def from_linear(linear: np.ndarray, transfer: str) -> np.ndarray:
    """Linear light → 8-bit code values."""
    v = _encode(np.clip(linear, 0, 1), transfer)
    return np.clip(np.rint(v * 255), 0, 255).astype(np.uint8)
