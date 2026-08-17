import os
from unittest.mock import patch
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import corax_wallet_setup


@pytest.fixture
def rsa_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from cryptography.hazmat.primitives import serialization

    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key_pem.decode("utf-8")


@patch("corax_wallet_setup.os.environ.get")
@patch("corax_wallet_setup.print")
def test_main_missing_api_key(mock_print, mock_env_get):
    mock_env_get.return_value = None
    corax_wallet_setup.main()
    mock_print.assert_called_with("❌ Fel: Du måste exportera CIRCLE_API_KEY!")


@patch("corax_wallet_setup.os.environ.get")
@patch("corax_wallet_setup.fetch_public_key")
@patch("corax_wallet_setup.print")
def test_main_fetch_key_failure(mock_print, mock_fetch, mock_env_get):
    mock_env_get.return_value = "fake_api_key"
    mock_fetch.side_effect = Exception("Fetch error")

    corax_wallet_setup.main()

    mock_fetch.assert_called_once()
    mock_print.assert_any_call("❌ Ett fel uppstod: Fetch error")


@patch("corax_wallet_setup.os.environ.get")
@patch("corax_wallet_setup.fetch_public_key")
@patch("corax_wallet_setup.register_entity_secret")
@patch("corax_wallet_setup.setup_wallet_infrastructure")
@patch("corax_wallet_setup.save_recovery_file")
@patch("corax_wallet_setup.set_key")
@patch("corax_wallet_setup.print")
def test_main_success(
    mock_print,
    mock_set_key,
    mock_save_recovery_file,
    mock_setup_wallet_infrastructure,
    mock_register,
    mock_fetch,
    mock_env_get,
    rsa_key_pair,
):
    private_key, pub_key_pem = rsa_key_pair
    mock_env_get.return_value = "fake_api_key"
    mock_fetch.return_value = pub_key_pem
    mock_register.return_value = "fake_recovery_data"
    mock_setup_wallet_infrastructure.return_value = (
        "TEST_WALLET_SET_ID",
        "TEST_WALLET_ID",
        "0xTESTADDRESS",
    )

    corax_wallet_setup.main()

    mock_fetch.assert_called_once()
    mock_register.assert_called_once()
    mock_setup_wallet_infrastructure.assert_called_once()

    mock_save_recovery_file.assert_called_once_with(
        "recovery.dat", "fake_recovery_data"
    )

    # We can't know the exact secret since secrets.token_hex is not mocked,
    # but we can verify it was called with the right .env path.
    # The actual call args check would be complicated due to non-mocked secret.
    assert mock_set_key.call_count == 1
    assert mock_set_key.call_args[0][0] == ".env"
    assert mock_set_key.call_args[0][1] == "CIRCLE_ENTITY_SECRET"


def test_if_name_main():
    import subprocess
    import sys

    env_exists = os.path.exists(".env")
    if env_exists:
        os.rename(".env", ".env.bak")

    try:
        result = subprocess.run(
            [sys.executable, "corax_wallet_setup.py"],
            capture_output=True,
            text=True,
            env={},
        )
        assert "❌ Fel: Du måste exportera CIRCLE_API_KEY!" in result.stdout
    finally:
        if env_exists:
            os.rename(".env.bak", ".env")
