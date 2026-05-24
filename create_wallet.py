import os
import requests
import base64
import secrets
import uuid
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from dotenv import load_dotenv

load_dotenv()


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
    api_key = os.getenv("CIRCLE_API_KEY")
    if not api_key:
        print("❌ Saknar CIRCLE_API_KEY i .env!")
        return

    # HÄR ÄR MAGIN: Vi utger oss för att vara en riktig webbläsare för att komma förbi Cloudflare (403)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    print("🔑 1. Din Entity Secret genererad!")
    entity_secret = secrets.token_hex(32)

    print("🔄 2. Hämtar Circles publika RSA-nyckel...")
    res = requests.get(
        "https://api.circle.com/v1/w3s/config/entity/publicKey", headers=headers
    )
    if not res.ok:
        print(f"❌ Fel vid public key: {res.status_code} - {res.text}")
        return
    public_key_pem = res.json()["data"]["publicKey"]

    print("🔄 3. Krypterar hemligheten...")
    ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)

    print("\n" + "!" * 50)
    print("🚨 MANUELL REGISTRERING KRÄVS I BROWSERN 🚨")
    print("1. Gå till Circle Console -> Developer Controlled -> Configurator")
    print("2. Klicka på 'Get Started' eller 'Set up entity secret'")
    print("3. När den frågar efter din 'Ciphertext', klistra in EXAKT denna text:")
    print("\n" + ciphertext + "\n")
    print("4. Klicka dig igenom, ladda ner 'recovery.dat' och slutför.")
    print("!" * 50 + "\n")

    input("👉 TRYCK ENTER HÄR NÄR DU ÄR KLAR I BROWSERN...")

    print("\n🔄 4. Skapar Wallet Set...")
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
    if not set_res.ok:
        print("❌ Fel vid Wallet Set:", set_res.text)
        return
    wallet_set_id = set_res.json()["data"]["walletSet"]["id"]
    print("✅ Wallet Set skapat!")

    print("🔄 5. Skapar Arc Testnet Plånbok...")
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
    if not wallet_res.ok:
        print("❌ Fel vid plånboksskapande:", wallet_res.text)
        return

    wallet_id = wallet_res.json()["data"]["wallets"][0]["id"]
    wallet_address = wallet_res.json()["data"]["wallets"][0]["address"]

    print("\n" + "=" * 60)
    print("🎉 SUCCÉ! ALLT ÄR KLART FÖR AGENTEN!")
    print("👉 1. Klistra in detta i din .env-fil i VScode:")
    print(f"CIRCLE_ENTITY_SECRET={entity_secret}")
    print(f"CIRCLE_WALLET_ID={wallet_id}")
    print("\n👉 2. Din publika Arc-adress (Använd denna i Fauceten!):")
    print(f"{wallet_address}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
