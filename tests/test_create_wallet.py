from unittest.mock import patch
import create_wallet


@patch("create_wallet.os.getenv")
@patch("create_wallet.print")
def test_main_missing_api_key(mock_print, mock_getenv):
    mock_getenv.return_value = None
    create_wallet.main()
    mock_print.assert_called_with("❌ Saknar CIRCLE_API_KEY i .env!")


@patch("create_wallet.input", return_value="")
@patch("create_wallet.encrypt_entity_secret", return_value="mock_ciphertext")
@patch("create_wallet.secrets.token_hex", return_value="mock_secret")
@patch("create_wallet.fetch_public_key")
@patch("create_wallet.os.getenv")
@patch("create_wallet.print")
def test_main_public_key_request_failure(
    mock_print, mock_getenv, mock_fetch, mock_token_hex, mock_encrypt, mock_input
):
    mock_getenv.return_value = "fake_api_key"
    mock_fetch.side_effect = Exception("403 - Forbidden")

    create_wallet.main()

    mock_fetch.assert_called_once()
    mock_print.assert_any_call("❌ Fel vid public key: 403 - Forbidden")


@patch("create_wallet.input", return_value="")
@patch("create_wallet.encrypt_entity_secret", return_value="mock_ciphertext")
@patch("create_wallet.secrets.token_hex", return_value="mock_secret")
@patch("create_wallet.setup_wallet_infrastructure")
@patch("create_wallet.fetch_public_key", return_value="mock_pub_key")
@patch("create_wallet.os.getenv")
@patch("create_wallet.print")
def test_main_wallet_creation_failure(
    mock_print,
    mock_getenv,
    mock_fetch,
    mock_setup_wallet_infrastructure,
    mock_token_hex,
    mock_encrypt,
    mock_input,
):
    mock_getenv.return_value = "fake_api_key"
    mock_setup_wallet_infrastructure.side_effect = Exception("Wallet creation failed")

    create_wallet.main()

    mock_setup_wallet_infrastructure.assert_called_once()
    mock_print.assert_any_call("❌ Fel vid plånboksskapande: Wallet creation failed")


@patch("create_wallet.set_key")
@patch("create_wallet.input", return_value="")
@patch("create_wallet.encrypt_entity_secret", return_value="mock_ciphertext")
@patch("create_wallet.secrets.token_hex", return_value="mock_secret")
@patch(
    "create_wallet.setup_wallet_infrastructure",
    return_value=("mock_wallet_set_id", "mock_wallet_id", "mock_address"),
)
@patch("create_wallet.fetch_public_key", return_value="mock_pub_key")
@patch("create_wallet.os.getenv")
@patch("create_wallet.print")
def test_main_success(
    mock_print,
    mock_getenv,
    mock_fetch,
    mock_setup_wallet_infrastructure,
    mock_token_hex,
    mock_encrypt,
    mock_input,
    mock_set_key,
):
    mock_getenv.return_value = "fake_api_key"

    create_wallet.main()

    mock_setup_wallet_infrastructure.assert_called_once()
    mock_set_key.assert_any_call(".env", "CIRCLE_ENTITY_SECRET", "mock_secret")
    mock_set_key.assert_any_call(".env", "CIRCLE_WALLET_ID", "mock_wallet_id")
    mock_print.assert_any_call("mock_address")


def test_if_name_main():
    import subprocess
    import sys
    import os

    env_exists = os.path.exists(".env")
    if env_exists:
        os.rename(".env", ".env.bak")

    try:
        result = subprocess.run(
            [sys.executable, "create_wallet.py"], capture_output=True, text=True, env={}
        )
        assert "Saknar CIRCLE_API_KEY i .env" in result.stdout
    finally:
        if env_exists:
            os.rename(".env.bak", ".env")
