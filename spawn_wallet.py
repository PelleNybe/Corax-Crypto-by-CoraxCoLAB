import os
from core.circle_api import fetch_public_key, setup_wallet_infrastructure
from core.crypto_utils import encrypt_entity_secret


def main():
    api_key = os.environ.get("CIRCLE_API_KEY")
    entity_secret = os.environ.get("CIRCLE_ENTITY_SECRET")

    if not api_key or not entity_secret:
        print("❌ Saknar CIRCLE_API_KEY eller CIRCLE_ENTITY_SECRET i minnet!")
        return

    print("🔄 1. Hämtar Circles publika RSA-nyckel...")
    public_key_pem = fetch_public_key(api_key)

    ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)

    print("🔄 2. Skapar Wallet Set och Arc Testnet Plånbok...")
    wallet_set_id, wallet_id, wallet_address = setup_wallet_infrastructure(
        api_key, ciphertext
    )
    print(f"✅ Wallet Set skapat med ID: {wallet_set_id}")

    print("\n" + "=" * 60)
    print("🎉 BINGO! PLÅNBOKEN ÄR ONLINE!")
    print("👉 1. Lägg in detta i din .env-fil i VScode:")
    print(f"CIRCLE_WALLET_ID={wallet_id}")
    print("\n👉 2. Din publika Arc-adress (Kopiera denna till Fauceten!):")
    print(f"{wallet_address}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
