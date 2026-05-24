import os
import requests
import base64
import uuid
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def encrypt_entity_secret(entity_secret, public_key_pem):
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


def main():
    api_key = os.environ.get("CIRCLE_API_KEY")
    entity_secret = os.environ.get("CIRCLE_ENTITY_SECRET")

    if not api_key or not entity_secret:
        print("❌ Saknar CIRCLE_API_KEY eller CIRCLE_ENTITY_SECRET i minnet!")
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    print("🔄 1. Hämtar Circles publika RSA-nyckel...")
    res = requests.get(
        "https://api.circle.com/v1/w3s/config/entity/publicKey", headers=headers
    )
    res.raise_for_status()
    public_key_pem = res.json()["data"]["publicKey"]

    print("🔄 2. Skapar Wallet Set (Corax Arbitrage Set)...")
    set_payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "name": "Corax Arbitrage Set",
        "entitySecretCiphertext": encrypt_entity_secret(entity_secret, public_key_pem),
    }
    set_res = requests.post(
        "https://api.circle.com/v1/w3s/developer/walletSets",
        headers=headers,
        json=set_payload,
    )
    set_res.raise_for_status()
    wallet_set_id = set_res.json()["data"]["walletSet"]["id"]
    print(f"✅ Wallet Set skapat med ID: {wallet_set_id}")

    print("🔄 3. Skapar din Arc Testnet Plånbok...")
    wallet_payload = {
        "idempotencyKey": str(uuid.uuid4()),
        "blockchains": ["ARC-TESTNET"],
        "count": 1,
        "walletSetId": wallet_set_id,
        "accountType": "EOA",
        "entitySecretCiphertext": encrypt_entity_secret(entity_secret, public_key_pem),
    }
    wallet_res = requests.post(
        "https://api.circle.com/v1/w3s/developer/wallets",
        headers=headers,
        json=wallet_payload,
    )
    wallet_res.raise_for_status()

    wallet_id = wallet_res.json()["data"]["wallets"][0]["id"]
    wallet_address = wallet_res.json()["data"]["wallets"][0]["address"]

    print("\n" + "=" * 60)
    print("🎉 BINGO! PLÅNBOKEN ÄR ONLINE!")
    print("👉 1. Lägg in detta i din .env-fil i VScode:")
    print(f"CIRCLE_WALLET_ID={wallet_id}")
    print("\n👉 2. Din publika Arc-adress (Kopiera denna till Fauceten!):")
    print(f"{wallet_address}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
