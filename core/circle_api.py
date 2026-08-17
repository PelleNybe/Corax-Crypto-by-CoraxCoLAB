import httpx
import uuid
from typing import Tuple

CIRCLE_API_BASE = "https://api.circle.com/v1/w3s"


def get_circle_headers(api_key: str) -> dict:
    """Returns the standard headers required for Circle API calls."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }


def fetch_public_key(api_key: str) -> str:
    """Fetches the Circle public RSA key."""
    headers = get_circle_headers(api_key)
    res = httpx.get(f"{CIRCLE_API_BASE}/config/entity/publicKey", headers=headers)
    res.raise_for_status()
    return res.json()["data"]["publicKey"]


def register_entity_secret(api_key: str, ciphertext: str) -> str:
    """Registers the entity secret ciphertext and returns the recovery file data."""
    headers = get_circle_headers(api_key)
    reg_payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCiphertext": ciphertext,
    }
    reg_res = httpx.post(
        f"{CIRCLE_API_BASE}/config/entity/secret", headers=headers, json=reg_payload
    )
    reg_res.raise_for_status()
    return reg_res.json()["data"]["recoveryFile"]


def create_wallet_set(
    api_key: str, ciphertext: str, name: str = "Corax Arbitrage Set"
) -> str:
    """Creates a wallet set and returns its ID."""
    headers = get_circle_headers(api_key)
    set_payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "name": name,
        "entitySecretCiphertext": ciphertext,
    }
    set_res = httpx.post(
        f"{CIRCLE_API_BASE}/developer/walletSets",
        headers=headers,
        json=set_payload,
    )
    set_res.raise_for_status()
    return set_res.json()["data"]["walletSet"]["id"]


def create_wallet(api_key: str, wallet_set_id: str, ciphertext: str) -> Tuple[str, str]:
    """Creates a wallet in the given wallet set and returns (wallet_id, wallet_address)."""
    headers = get_circle_headers(api_key)
    wallet_payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "blockchains": ["ARC-TESTNET"],
        "count": 1,
        "walletSetId": wallet_set_id,
        "accountType": "EOA",
        "entitySecretCiphertext": ciphertext,
    }
    wallet_res = httpx.post(
        f"{CIRCLE_API_BASE}/developer/wallets",
        headers=headers,
        json=wallet_payload,
    )
    wallet_res.raise_for_status()
    wallet_id = wallet_res.json()["data"]["wallets"][0]["id"]
    wallet_address = wallet_res.json()["data"]["wallets"][0]["address"]
    return wallet_id, wallet_address


def setup_wallet_infrastructure(api_key: str, ciphertext: str) -> Tuple[str, str, str]:
    """
    Creates a wallet set and a wallet, returning their IDs and the wallet address.
    """
    wallet_set_id = create_wallet_set(api_key, ciphertext)
    wallet_id, wallet_address = create_wallet(api_key, wallet_set_id, ciphertext)
    return wallet_set_id, wallet_id, wallet_address
