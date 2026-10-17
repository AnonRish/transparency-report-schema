"""Ed25519 keys, SHA-256 and strict base64."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

KEY_ID_PREFIX = "ed25519:"


class CryptoError(ValueError):
    """Malformed key, signature or encoding."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64decode_strict(text: str) -> bytes:
    """Decode standard base64, rejecting any non-canonical spelling of the same bytes."""
    if not isinstance(text, str):
        raise CryptoError("base64 value must be a string")
    try:
        raw = base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise CryptoError("invalid base64") from exc
    if base64.b64encode(raw).decode("ascii") != text:
        raise CryptoError("non-canonical base64")
    return raw


@dataclass(frozen=True)
class PublicKey:
    """An Ed25519 public key (32 raw bytes)."""

    raw: bytes

    def __post_init__(self) -> None:
        if len(self.raw) != 32:
            raise CryptoError("an Ed25519 public key is exactly 32 bytes")

    @property
    def key_id(self) -> str:
        """Self-certifying identifier: ``ed25519:`` plus 128 bits of SHA-256(key)."""
        return KEY_ID_PREFIX + sha256_hex(self.raw)[:32]

    def verify(self, message: bytes, signature: bytes) -> bool:
        if len(signature) != 64:
            return False
        try:
            Ed25519PublicKey.from_public_bytes(self.raw).verify(signature, message)
        except (InvalidSignature, ValueError):
            return False
        return True

    def to_b64(self) -> str:
        return b64encode(self.raw)

    @classmethod
    def from_b64(cls, text: str) -> PublicKey:
        return cls(b64decode_strict(text))


class KeyPair:
    """An Ed25519 signing key."""

    def __init__(self, private: Ed25519PrivateKey) -> None:
        self._private = private
        self.public = PublicKey(
            private.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        )

    @classmethod
    def generate(cls) -> KeyPair:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> KeyPair:
        """Deterministic key from a 32-byte seed (test vectors only)."""
        if len(seed) != 32:
            raise CryptoError("an Ed25519 seed is exactly 32 bytes")
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def from_pem(cls, pem: bytes, passphrase: bytes | None = None) -> KeyPair:
        try:
            key = serialization.load_pem_private_key(pem, password=passphrase)
        except (ValueError, TypeError) as exc:
            raise CryptoError(f"cannot load private key: {exc}") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise CryptoError("not an Ed25519 private key")
        return cls(key)

    def to_pem(self, passphrase: bytes | None = None) -> bytes:
        encryption: serialization.KeySerializationEncryption = (
            serialization.BestAvailableEncryption(passphrase)
            if passphrase
            else serialization.NoEncryption()
        )
        return self._private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
        )

    def sign(self, message: bytes) -> bytes:
        return self._private.sign(message)
