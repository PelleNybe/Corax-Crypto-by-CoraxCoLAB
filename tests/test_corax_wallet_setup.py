import pytest
import base64
import os
from unittest.mock import patch, MagicMock

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

from corax_wallet_setup import encrypt_entity_secret, main

@pytest.fixture
def rsa_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return private_key, public_pem

def test_encrypt_entity_secret(rsa_key_pair):
    private_key, public_pem = rsa_key_pair
    entity_secret_hex = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    encrypted_base64 = encrypt_entity_secret(entity_secret_hex, public_pem)

    # Decrypt and verify
    encrypted_bytes = base64.b64decode(encrypted_base64)
    decrypted_bytes = private_key.decrypt(
        encrypted_bytes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    assert decrypted_bytes.hex() == entity_secret_hex

@patch("corax_wallet_setup.os.environ.get")
@patch("builtins.print")
def test_main_missing_api_key(mock_print, mock_env_get):
    mock_env_get.return_value = None

    main()

    mock_print.assert_called_with("❌ Fel: Du måste exportera CIRCLE_API_KEY!")

@patch("corax_wallet_setup.os.environ.get")
@patch("corax_wallet_setup.requests.get")
@patch("corax_wallet_setup.requests.post")
@patch("builtins.open")
def test_main_success(mock_open, mock_post, mock_get, mock_env_get, rsa_key_pair):
    _, public_pem = rsa_key_pair
    mock_env_get.return_value = "TEST_API_KEY"

    # Mock responses
    mock_get_resp = MagicMock()
    mock_get_resp.json.return_value = {"data": {"publicKey": public_pem}}
    mock_get.return_value = mock_get_resp

    mock_post_reg_resp = MagicMock()
    mock_post_reg_resp.json.return_value = {"data": {"recoveryFile": "TEST_RECOVERY_DATA"}}

    mock_post_set_resp = MagicMock()
    mock_post_set_resp.json.return_value = {"data": {"walletSet": {"id": "TEST_WALLET_SET_ID"}}}

    mock_post_wallet_resp = MagicMock()
    mock_post_wallet_resp.json.return_value = {"data": {"wallets": [{"id": "TEST_WALLET_ID", "address": "0xTESTADDRESS"}]}}

    mock_post.side_effect = [mock_post_reg_resp, mock_post_set_resp, mock_post_wallet_resp]

    main()

    # Verify open was called
    mock_open.assert_called_with("recovery.dat", "w")

@patch("corax_wallet_setup.os.environ.get")
@patch("corax_wallet_setup.requests.get")
@patch("builtins.print")
def test_main_api_exception(mock_print, mock_get, mock_env_get):
    mock_env_get.return_value = "TEST_API_KEY"

    mock_get.side_effect = Exception("TEST EXCEPTION")

    main()

    mock_print.assert_any_call("❌ Ett fel uppstod: TEST EXCEPTION")
