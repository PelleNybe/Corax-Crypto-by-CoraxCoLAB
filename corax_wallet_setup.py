import os
import requests
import base64
import secrets
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
    if not api_key:
        print("❌ Fel: Du måste exportera CIRCLE_API_KEY!")
        return

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        print("🔄 1. Genererar 32-byte Entity Secret...")
        entity_secret = secrets.token_hex(32)

        print("🔄 2. Hämtar Circles publika RSA-nyckel...")
        res = requests.get(
            "https://api.circle.com/v1/w3s/config/entity/publicKey", headers=headers
        )
        res.raise_for_status()
        public_key_pem = res.json()["data"]["publicKey"]

        print("🔄 3. Registrerar hemligheten hos Circle...")
        reg_payload = {
            "idempotencyKey": str(uuid.uuid4()),
            "entitySecretCiphertext": encrypt_entity_secret(
                entity_secret, public_key_pem
            ),
        }
        reg_res = requests.post(
            "https://api.circle.com/v1/w3s/config/entity/secret",
            headers=headers,
            json=reg_payload,
        )
        reg_res.raise_for_status()

        # Spara recovery-filen
        with open("recovery.dat", "w") as f:
            f.write(reg_res.json()["data"]["recoveryFile"])

        print("🔄 4. Skapar Wallet Set (Corax Arbitrage Set)...")
        set_payload = {
            "idempotencyKey": str(uuid.uuid4()),
            "name": "Corax Arbitrage Set",
            "entitySecretCiphertext": encrypt_entity_secret(
                entity_secret, public_key_pem
            ),
        }
        set_res = requests.post(
            "https://api.circle.com/v1/w3s/walletSets",
            headers=headers,
            json=set_payload,
        )
        set_res.raise_for_status()
        wallet_set_id = set_res.json()["data"]["walletSet"]["id"]

        print("🔄 5. Skapar din Arc Testnet Plånbok...")
        wallet_payload = {
            "idempotencyKey": str(uuid.uuid4()),
            "blockchains": ["ARC-TESTNET"],
            "count": 1,
            "walletSetId": wallet_set_id,
            "accountType": "EOA",
            "entitySecretCiphertext": encrypt_entity_secret(
                entity_secret, public_key_pem
            ),
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
        print("🎉 BINGO! ALLT ÄR KLART FÖR AGENTEN!")
        print("👉 1. Klistra in detta i din .env-fil i VScode:")
        print(f"CIRCLE_ENTITY_SECRET={entity_secret}")
        print(f"CIRCLE_WALLET_ID={wallet_id}")
        print("\n👉 2. Din publika Arc-adress (Använd denna i Fauceten!):")
        print(f"{wallet_address}")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"❌ Ett fel uppstod: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Detaljer: {e.response.text}")


if __name__ == "__main__":
    main()
