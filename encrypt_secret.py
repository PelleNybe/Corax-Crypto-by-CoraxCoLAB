import secrets

import os
import httpx
from dotenv import load_dotenv, set_key
from core.crypto_utils import encrypt_entity_secret

load_dotenv()


def get_public_key_pem():
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
                res = httpx.get(
                    "https://api.circle.com/v1/w3s/config/entity/publicKey",
                    headers=headers,
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
    return public_key_pem


def main():
    public_key_pem = get_public_key_pem()
    print("\n" + "=" * 50)
    print("🔄 1. Genererar 32-byte Entity Secret...")
    entity_secret = secrets.token_hex(32)
    print("🔑 DIN ENTITY SECRET har genererats och sparats automatiskt i .env filen.")
    set_key(".env", "CIRCLE_ENTITY_SECRET", entity_secret)

    print("🔄 2. Krypterar lokalt (helt offline)...")
    try:
        ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)
        print("✅ Kryptering lyckades!")
        print("\n🚨 KLISTRA IN DENNA CIPHERTEXT I CIRCLE CONSOLE:")
        print("\n" + ciphertext + "\n")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"❌ Fel vid kryptering: {e}")


if __name__ == "__main__":  # pragma: no cover
    main()
