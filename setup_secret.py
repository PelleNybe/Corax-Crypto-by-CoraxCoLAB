import os
import requests
import base64
import secrets
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key


def generate_entity_secret():
    return secrets.token_hex(32)


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

    print("🔄 1. Genererar 32-byte Entity Secret...")
    entity_secret = generate_entity_secret()

    print("\n" + "=" * 50)
    print("🔑 DIN ENTITY SECRET (KOPIERA IN I .env sen):")
    print(entity_secret)
    print("=" * 50 + "\n")

    print("🔄 2. Hämtar Circles publika RSA-nyckel...")
    try:
        res = requests.get(
            "https://api.circle.com/v1/w3s/config/entity/publicKey", headers=headers
        )
        res.raise_for_status()
        public_key_pem = res.json()["data"]["publicKey"]

        print("🔄 3. Krypterar hemligheten...")
        ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)

        print("🔄 4. Registrerar hemligheten hos Circle...")
        reg_payload = {
            "idempotencyKey": secrets.token_hex(16),
            "entitySecretCiphertext": ciphertext,
        }
        reg_res = requests.post(
            "https://api.circle.com/v1/w3s/config/entity/secret",
            headers=headers,
            json=reg_payload,
        )
        reg_res.raise_for_status()

        print("🎉 SUCCÉ! Din Entity Secret är registrerad!")
        recovery_file = reg_res.json()["data"]["recoveryFile"]

        with open("recovery.dat", "w") as f:
            f.write(recovery_file)
        print("👉 recovery.dat har sparats. Göm den väl!")

    except Exception as e:
        print(f"❌ Ett fel uppstod: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Detaljer: {e.response.text}")


if __name__ == "__main__":
    main()
