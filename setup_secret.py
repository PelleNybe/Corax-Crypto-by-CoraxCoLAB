import os
import secrets
from loguru import logger
from dotenv import set_key
from core.circle_api import fetch_public_key, register_entity_secret
from core.crypto_utils import encrypt_entity_secret, save_recovery_file


def generate_entity_secret():
    return secrets.token_hex(32)


def main():
    api_key = os.environ.get("CIRCLE_API_KEY")
    if not api_key:
        logger.error("❌ Fel: Du måste exportera CIRCLE_API_KEY!")
        return
    logger.info("🔄 1. Genererar 32-byte Entity Secret...")
    entity_secret = generate_entity_secret()
    logger.info(
        "🔑 DIN ENTITY SECRET har genererats och sparats automatiskt i .env filen."
    )
    set_key(".env", "CIRCLE_ENTITY_SECRET", entity_secret)
    logger.info("🔄 2. Hämtar Circles publika RSA-nyckel...")
    try:
        public_key_pem = fetch_public_key(api_key)
        logger.info("🔄 3. Krypterar hemligheten...")
        ciphertext = encrypt_entity_secret(entity_secret, public_key_pem)
        logger.info("🔄 4. Registrerar hemligheten hos Circle...")
        recovery_file = register_entity_secret(api_key, ciphertext)
        logger.success("🎉 SUCCÉ! Din Entity Secret är registrerad!")
        # Save with strict permissions (0600)
        save_recovery_file("recovery.dat", recovery_file)
        logger.info("👉 recovery.dat har sparats. Göm den väl!")
    except Exception as e:
        logger.error(f"❌ Ett fel uppstod: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Detaljer: {e.response.text}")


if __name__ == "__main__":
    main()
