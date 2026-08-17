import os
import base64
import pytest
from core.crypto_utils import save_recovery_file, encrypt_entity_secret
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes


def test_save_recovery_file_success(mocker):
    # Mock os.open to return a dummy file descriptor
    original_open = os.open

    def mock_open_side_effect(path, flags, mode=0o777, *, dir_fd=None):
        if path == "test_recovery.txt":
            return 42
        return original_open(path, flags, mode, dir_fd=dir_fd)

    mock_open = mocker.patch("os.open", side_effect=mock_open_side_effect)
    # Mock os.fdopen
    mock_fdopen = mocker.patch("os.fdopen")

    mock_file_obj = mock_fdopen.return_value.__enter__.return_value

    save_recovery_file("test_recovery.txt", "secret_data")

    # Verify os.open was called with correct flags
    mock_open.assert_any_call(
        "test_recovery.txt", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600
    )

    # Verify fdopen was called with the descriptor and 'w' mode
    mock_fdopen.assert_called_once_with(42, "w")

    # Verify write was called with the correct data
    mock_file_obj.write.assert_called_once_with("secret_data")


def test_save_recovery_file_exception(mocker):
    original_open = os.open

    def mock_open_side_effect(path, flags, mode=0o777, *, dir_fd=None):
        if path == "test_recovery.txt":
            return 42
        return original_open(path, flags, mode, dir_fd=dir_fd)

    mocker.patch("os.open", side_effect=mock_open_side_effect)
    mock_fdopen = mocker.patch("os.fdopen")
    mock_close = mocker.patch("os.close")

    mock_file_obj = mock_fdopen.return_value.__enter__.return_value

    # Force write to raise an exception
    mock_file_obj.write.side_effect = Exception("Write failed")

    with pytest.raises(Exception, match="Write failed"):
        save_recovery_file("test_recovery.txt", "secret_data")

    # Verify close was called due to the exception
    mock_close.assert_any_call(42)


def test_encrypt_entity_secret(mocker):
    # Mock load_pem_public_key and its returned public_key
    mock_load_pem = mocker.patch("core.crypto_utils.load_pem_public_key")
    mock_public_key = mock_load_pem.return_value
    mock_public_key.encrypt.return_value = b"encrypted_bytes"

    # Call the function
    result = encrypt_entity_secret("0123456789abcdef", "dummy_pem")

    # Verify load_pem_public_key was called correctly
    mock_load_pem.assert_called_once_with(b"dummy_pem")

    # Verify encrypt was called with the decoded hex and correct padding
    mock_public_key.encrypt.assert_called_once()
    args, kwargs = mock_public_key.encrypt.call_args

    assert args[0] == bytes.fromhex("0123456789abcdef")

    # Verify the padding argument is correctly configured OAEP
    pad = args[1]
    assert isinstance(pad, padding.OAEP)
    assert isinstance(pad._mgf, padding.MGF1)
    assert isinstance(pad._mgf._algorithm, hashes.SHA256)
    assert isinstance(pad._algorithm, hashes.SHA256)
    assert pad._label is None

    # Verify base64 output
    assert result == base64.b64encode(b"encrypted_bytes").decode("utf-8")


def test_encrypt_entity_secret_invalid_hex(mocker):
    # Pass an invalid hex string (e.g., odd length or non-hex characters)
    with pytest.raises(ValueError):
        encrypt_entity_secret("invalid_hex_string", "dummy_pem")


def test_encrypt_entity_secret_invalid_pem(mocker):
    # Mock load_pem_public_key to raise ValueError to simulate an invalid PEM
    mock_load_pem = mocker.patch(
        "core.crypto_utils.load_pem_public_key",
        side_effect=ValueError("Invalid PEM string"),
    )

    # Pass a valid hex string but an invalid PEM
    with pytest.raises(ValueError, match="Invalid PEM string"):
        encrypt_entity_secret("0123456789abcdef", "invalid_pem")

    # Verify load_pem_public_key was called correctly
    mock_load_pem.assert_called_once_with(b"invalid_pem")


def test_encrypt_entity_secret_encryption_failure(mocker):
    # Mock load_pem_public_key and its returned public_key
    mock_load_pem = mocker.patch("core.crypto_utils.load_pem_public_key")
    mock_public_key = mock_load_pem.return_value

    # Simulate an encryption failure (e.g., ValueError due to message too long)
    mock_public_key.encrypt.side_effect = ValueError("Encryption failed")

    # Pass a valid hex string and PEM, but expect the encryption to fail
    with pytest.raises(ValueError, match="Encryption failed"):
        encrypt_entity_secret("0123456789abcdef", "dummy_pem")

    # Verify load_pem_public_key was called correctly
    mock_load_pem.assert_called_once_with(b"dummy_pem")

    # Verify encrypt was called
    mock_public_key.encrypt.assert_called_once()
