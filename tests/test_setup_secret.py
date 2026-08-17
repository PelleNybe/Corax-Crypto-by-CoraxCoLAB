from unittest.mock import patch
from setup_secret import main


@patch("setup_secret.os.environ.get")
@patch("setup_secret.logger")
def test_main_missing_api_key(mock_logger, mock_env_get):
    mock_env_get.return_value = None
    main()
    mock_logger.error.assert_called_with("❌ Fel: Du måste exportera CIRCLE_API_KEY!")


@patch("setup_secret.os.environ.get")
@patch("setup_secret.fetch_public_key")
@patch("setup_secret.encrypt_entity_secret")
@patch("setup_secret.register_entity_secret")
@patch("setup_secret.save_recovery_file")
@patch("setup_secret.set_key")
@patch("setup_secret.logger")
def test_main_success(
    mock_logger,
    mock_set_key,
    mock_save_recovery_file,
    mock_register,
    mock_encrypt,
    mock_fetch,
    mock_env_get,
):

    mock_env_get.return_value = "TEST_API_KEY"
    mock_fetch.return_value = "TEST_PEM"
    mock_encrypt.return_value = "TEST_CIPHER"
    mock_register.return_value = "TEST_RECOVERY_DATA"

    main()

    mock_fetch.assert_called_once()
    mock_register.assert_called_once()
    mock_logger.success.assert_any_call("🎉 SUCCÉ! Din Entity Secret är registrerad!")


@patch("setup_secret.os.environ.get")
@patch("setup_secret.fetch_public_key")
@patch("setup_secret.logger")
def test_main_api_error(mock_logger, mock_fetch, mock_env_get):
    mock_env_get.return_value = "TEST_API_KEY"
    mock_fetch.side_effect = Exception("API Error")

    main()

    mock_logger.error.assert_any_call("❌ Ett fel uppstod: API Error")


@patch("setup_secret.os.environ.get")
@patch("setup_secret.fetch_public_key")
@patch("setup_secret.encrypt_entity_secret")
@patch("setup_secret.register_entity_secret")
@patch("setup_secret.save_recovery_file")
@patch("setup_secret.logger")
@patch("setup_secret.set_key")
def test_main_file_error(
    mock_set_key,
    mock_logger,
    mock_save_recovery_file,
    mock_register,
    mock_encrypt,
    mock_fetch,
    mock_env_get,
):
    mock_save_recovery_file.side_effect = Exception("File Error")
    mock_env_get.return_value = "TEST_API_KEY"
    mock_fetch.return_value = "TEST_PEM"
    mock_encrypt.return_value = "TEST_CIPHER"
    mock_register.return_value = "TEST_RECOVERY_DATA"

    main()

    mock_logger.error.assert_any_call("❌ Ett fel uppstod: File Error")
