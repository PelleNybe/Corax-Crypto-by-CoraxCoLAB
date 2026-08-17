import os
import aiohttp
from loguru import logger
from core.config import settings


class VaultManager:
    """
    Integrates with HashiCorp Vault to fetch sensitive secrets at runtime.
    This prevents storing API keys directly in .env files in production.
    """

    def __init__(self):
        self.vault_url = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
        self.vault_token = os.environ.get("VAULT_TOKEN")

    async def get_secret(self, path: str, key: str) -> str:
        """Fetches a secret from Vault using AppRole/Token."""
        if not self.vault_token:
            logger.warning(
                "No VAULT_TOKEN provided. Falling back to environment variables."
            )
            return getattr(settings, key.upper(), None)

        url = f"{self.vault_url}/v1/secret/data/{path}"
        headers = {"X-Vault-Token": self.vault_token}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        secret_value = data.get("data", {}).get("data", {}).get(key)
                        if secret_value:
                            logger.debug(f"Successfully fetched {key} from Vault.")
                            return secret_value
                    logger.error(
                        f"Failed to fetch {key} from Vault. Status: {response.status}"
                    )
        except Exception as e:
            logger.error(f"Vault connection error: {e}")

        return getattr(settings, key.upper(), None)


vault_manager = VaultManager()
