import os
import secrets
from dotenv import set_key
from core.circle_api import (
    fetch_public_key,
    register_entity_secret,
    setup_wallet_infrastructure,
)
from core.crypto_utils import encrypt_entity_secret, save_recovery_file


def main():
    api_key = os.environ.get("CIRCLE_API_KEY")
    if not api_key:
        print("❌ Fel: Du måste exportera CIRCLE_API_KEY!")
        return

    try:
        print("🔄 1. Genererar 32-byte Entity Secret...")
        entity_secret = secrets.token_hex(32)

        print("🔄 2. Hämtar Circles publika RSA-nyckel...")
        public_key_pem = fetch_public_key(api_key)
        ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)

        print("🔄 3. Registrerar hemligheten hos Circle...")
        recovery_file_data = register_entity_secret(api_key, ciphertext)

        # Spara recovery-filen med säkra rättigheter (0600)
        save_recovery_file("recovery.dat", recovery_file_data)

        print("🔄 4. Skapar Wallet Set och Arc Testnet Plånbok...")
        wallet_set_id, wallet_id, wallet_address = setup_wallet_infrastructure(
            api_key, ciphertext
        )

        print("\n" + "=" * 60)
        print("🎉 BINGO! ALLT ÄR KLART FÖR AGENTEN!")
        print("👉 1. Klistra in detta i din .env-fil i VScode:")
        set_key(".env", "CIRCLE_ENTITY_SECRET", entity_secret)
        print("CIRCLE_ENTITY_SECRET har sparats i din .env-fil.")
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
