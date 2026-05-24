import secrets
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Hämta Circle API-nyckel för att dynamiskt hämta den publika nyckeln, eller fallback till lokal miljö
circle_api_key = os.environ.get("CIRCLE_API_KEY")
public_key_pem = os.environ.get("CIRCLE_PUBLIC_KEY")

if not public_key_pem:
    if circle_api_key:
        try:
            print("🔄 Hämtar Circles publika RSA-nyckel via API...")
            headers = {
                "Authorization": f"Bearer {circle_api_key}",
                "Content-Type": "application/json",
            }
            res = requests.get(
                "https://api.circle.com/v1/w3s/config/entity/publicKey", headers=headers
            )
            res.raise_for_status()
            public_key_pem = res.json()["data"]["publicKey"]
        except Exception as e:
            print(f"❌ Fel vid hämtning av publik nyckel via API: {e}")

    if not public_key_pem:
        try:
            with open("circle_public_key.pem", "r") as f:
                public_key_pem = f.read()
        except FileNotFoundError:
            print(
                "❌ Fel: Kunde inte hämta publik nyckel via API och varken CIRCLE_PUBLIC_KEY eller circle_public_key.pem finns."
            )
            exit(1)



def encrypt_entity_secret(entity_secret, pem_key):
    public_key = load_pem_public_key(pem_key.encode("utf-8"))
    ciphertext = public_key.encrypt(
        bytes.fromhex(entity_secret),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("utf-8")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🔄 1. Genererar 32-byte Entity Secret...")
    entity_secret = secrets.token_hex(32)
    print(f"🔑 DIN ENTITY SECRET (SPARA DENNA I .env): \n{entity_secret}\n")

    print("🔄 2. Krypterar lokalt (helt offline)...")
    try:
        ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)
        print("✅ Kryptering lyckades!")
        print("\n🚨 KLISTRA IN DENNA CIPHERTEXT I CIRCLE CONSOLE:")
        print("\n" + ciphertext + "\n")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"❌ Fel vid kryptering: {e}")
