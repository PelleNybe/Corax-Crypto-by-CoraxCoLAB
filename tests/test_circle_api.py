import pytest
from unittest.mock import Mock
from core.circle_api import create_wallet, CIRCLE_API_BASE


def test_create_wallet_success(mocker):
    # Mock httpx.post
    mock_post = mocker.patch("core.circle_api.httpx.post")

    # Setup mock response
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {
            "wallets": [{"id": "test_wallet_id_123", "address": "0xTestAddress456"}]
        }
    }
    mock_response.raise_for_status = Mock()
    mock_post.return_value = mock_response

    # Mock uuid to have a predictable idempotencyKey
    mock_uuid = mocker.patch("core.circle_api.uuid.uuid4")
    mock_uuid.return_value = "test-uuid-0000"

    # Call the function
    wallet_id, wallet_address = create_wallet(
        api_key="test_api_key",
        wallet_set_id="test_wallet_set_id",
        ciphertext="test_ciphertext",
    )

    # Verify outputs
    assert wallet_id == "test_wallet_id_123"
    assert wallet_address == "0xTestAddress456"

    # Verify httpx.post was called with correct parameters
    expected_headers = {
        "Authorization": "Bearer test_api_key",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    expected_payload = {
        "idempotencyKey": "test-uuid-0000",
        "blockchains": ["ARC-TESTNET"],
        "count": 1,
        "walletSetId": "test_wallet_set_id",
        "accountType": "EOA",
        "entitySecretCiphertext": "test_ciphertext",
    }

    mock_post.assert_called_once_with(
        f"{CIRCLE_API_BASE}/developer/wallets",
        headers=expected_headers,
        json=expected_payload,
    )
    mock_response.raise_for_status.assert_called_once()


def test_create_wallet_http_error(mocker):
    # Mock httpx.post to raise an HTTPError
    mock_post = mocker.patch("core.circle_api.httpx.post")

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception(
        "401 Client Error: Unauthorized"
    )
    mock_post.return_value = mock_response

    # Call the function and expect an exception
    with pytest.raises(Exception, match="401 Client Error: Unauthorized"):
        create_wallet(
            api_key="invalid_api_key",
            wallet_set_id="test_wallet_set_id",
            ciphertext="test_ciphertext",
        )

    # Verify httpx.post was called
    mock_post.assert_called_once()
    mock_response.raise_for_status.assert_called_once()
