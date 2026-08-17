import os
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def encrypt_entity_secret(entity_secret: str, public_key_pem: str) -> str:
    """
    Encrypts a hex-encoded entity secret using an RSA public key PEM string.

    Args:
        entity_secret: The 32-byte hex-encoded secret.
        public_key_pem: The public key in PEM format.

    Returns:
        The base64-encoded ciphertext.
    """
    public_key = load_pem_public_key(public_key_pem.encode("utf-8"))
    ciphertext = public_key.encrypt(
        bytes.fromhex(entity_secret),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("utf-8")


def save_recovery_file(filename: str, file_data: str) -> None:
    """Saves recovery file data with strict permissions (0o600)."""
    fd = os.open(filename, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(file_data)
    except Exception:
        os.close(fd)
        raise
