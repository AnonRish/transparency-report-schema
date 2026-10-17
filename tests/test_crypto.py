from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from transparency_report_schema.crypto import (
    CryptoError,
    KeyPair,
    PublicKey,
    b64decode_strict,
    b64encode,
    sha256_hex,
)


def test_rfc8032_test_vector_1() -> None:
    """RFC 8032 section 7.1, TEST 1."""
    key = KeyPair.from_seed(
        bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    )
    assert (
        key.public.raw.hex() == "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    )
    assert key.sign(b"").hex() == (
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb88215"
        "90a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )


def test_sign_verify_and_rejection() -> None:
    key = KeyPair.generate()
    signature = key.sign(b"report")
    assert key.public.verify(b"report", signature)
    assert not key.public.verify(b"reporT", signature)
    assert not key.public.verify(b"report", signature[:-1])
    assert not KeyPair.generate().public.verify(b"report", signature)


def test_key_ids_and_validation() -> None:
    key = KeyPair.from_seed(bytes([7]) * 32)
    assert key.public.key_id == "ed25519:" + sha256_hex(key.public.raw)[:32]
    with pytest.raises(CryptoError):
        PublicKey(b"short")
    with pytest.raises(CryptoError):
        KeyPair.from_seed(b"short")
    assert PublicKey.from_b64(key.public.to_b64()) == key.public


def test_pem_round_trip_and_refusals() -> None:
    key = KeyPair.generate()
    assert KeyPair.from_pem(key.to_pem()).public == key.public
    encrypted = key.to_pem(b"pw")
    assert KeyPair.from_pem(encrypted, b"pw").public == key.public
    with pytest.raises(CryptoError):
        KeyPair.from_pem(encrypted, b"wrong")
    with pytest.raises(CryptoError):
        KeyPair.from_pem(b"nope")
    rsa_pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    with pytest.raises(CryptoError, match="Ed25519"):
        KeyPair.from_pem(rsa_pem)


def test_strict_base64() -> None:
    assert b64decode_strict(b64encode(b"hello")) == b"hello"
    for bad in ("QR==", "QQ=", "A A=", "\u00e9\u00e9\u00e9\u00e9", "AAE*"):
        with pytest.raises(CryptoError):
            b64decode_strict(bad)
    with pytest.raises(CryptoError):
        b64decode_strict(5)  # type: ignore[arg-type]
    assert base64.b64decode("QR==") == base64.b64decode("QQ==")
