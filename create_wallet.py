import os
import secrets
from dotenv import load_dotenv, set_key
from core.circle_api import fetch_public_key, setup_wallet_infrastructure
from core.crypto_utils import encrypt_entity_secret

load_dotenv()


def main():
    api_key = os.getenv("CIRCLE_API_KEY")
    if not api_key:
        print("❌ Saknar CIRCLE_API_KEY i .env!")
        return

    print("🔑 1. Din Entity Secret genererad! Sparar till .env...")
    entity_secret = secrets.token_hex(32)

    print("🔄 2. Hämtar Circles publika RSA-nyckel...")
    try:
        public_key_pem = fetch_public_key(api_key)
    except Exception as e:
        print(f"❌ Fel vid public key: {e}")
        return

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

    print("\n🔄 4. Skapar Wallet Set och Arc Testnet Plånbok...")
    try:
        wallet_set_id, wallet_id, wallet_address = setup_wallet_infrastructure(
            api_key, ciphertext
        )
    except Exception as e:
        print(f"❌ Fel vid plånboksskapande: {e}")
        return
    print("✅ Wallet Set skapat!")

    # Spara säkert till .env istället för att skriva ut hemligheter i terminalen
    env_file = ".env"
    set_key(env_file, "CIRCLE_ENTITY_SECRET", entity_secret)
    set_key(env_file, "CIRCLE_WALLET_ID", wallet_id)

    print("\n" + "=" * 60)
    print("🎉 SUCCÉ! ALLT ÄR KLART FÖR AGENTEN!")
    print("✅ CIRCLE_ENTITY_SECRET har sparats i din .env-fil.")
    print("✅ CIRCLE_WALLET_ID har sparats i din .env-fil.")
    print("\n👉 Din publika Arc-adress (Använd denna i Fauceten!):")
    print(f"{wallet_address}")
    print("=" * 60 + "\n")


if __name__ == "__main__":  # pragma: no cover
    main()
