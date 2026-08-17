from unittest.mock import patch, mock_open, MagicMock
from encrypt_secret import get_public_key_pem


def test_get_public_key_pem_from_env():
    with patch("os.environ.get") as mock_get:
        # Side effect to return the public key if asked for CIRCLE_PUBLIC_KEY
        def mock_env_get(key):
            if key == "CIRCLE_PUBLIC_KEY":
                return "env_pem_key"
            return None

        mock_get.side_effect = mock_env_get

        result = get_public_key_pem()
        assert result == "env_pem_key"


def test_get_public_key_pem_from_api():
    with patch("os.environ.get") as mock_get, patch("httpx.get") as mock_req_get:

        def mock_env_get(key):
            if key == "CIRCLE_API_KEY":
                return "test_api_key"
            return None

        mock_get.side_effect = mock_env_get

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"publicKey": "api_pem_key"}}
        mock_req_get.return_value = mock_resp

        result = get_public_key_pem()

        assert result == "api_pem_key"
        mock_req_get.assert_called_once()
        args, kwargs = mock_req_get.call_args
        assert args[0] == "https://api.circle.com/v1/w3s/config/entity/publicKey"
        assert kwargs["headers"]["Authorization"] == "Bearer test_api_key"


def test_get_public_key_pem_api_fails_fallback_to_file():
    with (
        patch("os.environ.get") as mock_get,
        patch("httpx.get") as mock_req_get,
        patch("builtins.open", mock_open(read_data="file_pem_key")) as mock_file,
    ):

        def mock_env_get(key):
            if key == "CIRCLE_API_KEY":
                return "test_api_key"
            return None

        mock_get.side_effect = mock_env_get

        # Make API fail
        mock_req_get.side_effect = Exception("API Error")

        result = get_public_key_pem()

        assert result == "file_pem_key"
        mock_file.assert_any_call("circle_public_key.pem", "r")


def test_get_public_key_pem_no_env_fallback_to_file():
    with (
        patch("os.environ.get") as mock_get,
        patch("builtins.open", mock_open(read_data="file_pem_key")) as mock_file,
    ):
        mock_get.return_value = None

        result = get_public_key_pem()

        assert result == "file_pem_key"
        mock_file.assert_any_call("circle_public_key.pem", "r")


def test_get_public_key_pem_all_fail_exits():
    with (
        patch("os.environ.get") as mock_get,
        patch("builtins.open") as mock_file,
        patch("builtins.exit") as mock_exit,
    ):
        mock_get.return_value = None

        # When `builtins.open` is mocked using MagicMock without mock_open,
        # we can just have side_effect throw FileNotFoundError.
        # But let's be careful about other files opened during test discovery/run.
        # So we create a custom side_effect that only raises for the target file.
        def mock_open_side_effect(filename, mode="r", *args, **kwargs):
            if filename == "circle_public_key.pem":
                raise FileNotFoundError("File not found")
            return mock_open()(filename, mode, *args, **kwargs)

        mock_file.side_effect = mock_open_side_effect

        get_public_key_pem()

        mock_exit.assert_called_once_with(1)


@patch("encrypt_secret.get_public_key_pem")
@patch("encrypt_secret.secrets.token_hex")
@patch("encrypt_secret.set_key")
@patch("encrypt_secret.encrypt_entity_secret")
@patch("builtins.print")
def test_main_success(
    mock_print, mock_encrypt, mock_set_key, mock_token_hex, mock_get_pem
):
    mock_get_pem.return_value = "fake_pem"
    mock_token_hex.return_value = "fake_secret_hex"
    mock_encrypt.return_value = "fake_ciphertext"

    from encrypt_secret import main

    main()

    mock_get_pem.assert_called_once()
    mock_token_hex.assert_called_once_with(32)
    mock_set_key.assert_called_once_with(
        ".env", "CIRCLE_ENTITY_SECRET", "fake_secret_hex"
    )
    mock_encrypt.assert_called_once_with("fake_secret_hex", "fake_pem")

    # Check that print was called with success messages
    mock_print.assert_any_call("✅ Kryptering lyckades!")
    mock_print.assert_any_call("\nfake_ciphertext\n")


@patch("encrypt_secret.get_public_key_pem")
@patch("encrypt_secret.secrets.token_hex")
@patch("encrypt_secret.set_key")
@patch("encrypt_secret.encrypt_entity_secret")
@patch("builtins.print")
def test_main_encryption_failure(
    mock_print, mock_encrypt, mock_set_key, mock_token_hex, mock_get_pem
):
    mock_get_pem.return_value = "fake_pem"
    mock_token_hex.return_value = "fake_secret_hex"
    mock_encrypt.side_effect = Exception("Encryption failed dummy")

    from encrypt_secret import main

    main()

    mock_get_pem.assert_called_once()
    mock_token_hex.assert_called_once_with(32)
    mock_set_key.assert_called_once_with(
        ".env", "CIRCLE_ENTITY_SECRET", "fake_secret_hex"
    )
    mock_encrypt.assert_called_once_with("fake_secret_hex", "fake_pem")

    # Check that print was called with failure message
    mock_print.assert_any_call("❌ Fel vid kryptering: Encryption failed dummy")
