import asyncio
import re
from loguru import logger
from typing import Dict, Any, Tuple, Optional
from core.config import settings
from schemas.tools import CCTPTransferToolSchema


class CoraxCopilot:
    """
    Asynchronous LLM Copilot bridge.
    Handles deep-context macro analysis without blocking the high-speed execution loop.
    Compatible with OpenAI/Gemini generic prompt interfaces.
    """

    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        self._cached_synthesis: Optional[str] = None
        self._last_state_hash: Optional[str] = None

    def get_tool_schemas(self):
        """Returns the JSON schema for tools available to the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "execute_cctp_transfer",
                    "description": "Instruct the agent to move USDC across chains using Circle's CCTP when a cross-chain arbitrage opportunity is detected.",
                    "parameters": CCTPTransferToolSchema.model_json_schema(),
                },
            }
        ]

    async def generate_synthesis(self, state_summary: Dict[str, Any]) -> str:
        """
        Queries an LLM API to generate a human-readable Market Synthesis.
        """
        regime = state_summary.get("regime", "UNKNOWN")

        recent_action = state_summary.get("recent_action", "HOLD")

        # Create a simple hash to check if state changed significantly
        state_hash = f"{regime}_{recent_action}"

        if self._last_state_hash == state_hash and self._cached_synthesis:
            return self._cached_synthesis

        await asyncio.sleep(1.5)

        logger.debug("LLM Prompt generated.")

        regime_messages = {
            "TRENDING_UP": "Copilot: Bullish momentum confirmed. Order flow supports continuation.",
            "VOLATILE_CRASH": "Copilot: Extreme downside volatility. Risk-off mode activated.",
            "RANGING": "Copilot: Market consolidating. Avoiding chop until volume expands.",
        }

        synthesis = regime_messages.get(
            regime, "Copilot: Analyzing micro-structure for clear direction..."
        )

        self._cached_synthesis = synthesis
        self._last_state_hash = state_hash
        return synthesis

    def _resolve_chain(self, chain_match: Optional[re.Match], default: str) -> str:
        """Helper to resolve chain names from regex matches."""
        if not chain_match:
            return default

        src = chain_match.group(1).lower()
        chain_mapping = {
            "optimism": "optimism_sepolia",
            "avalanche": "avalanche_fuji",
            "arbitrum": "arbitrum_sepolia",
            "solana": "solana_devnet",
            "base": "base_sepolia",
            "polygon": "polygon_amoy",
            "ethereum": "ethereum_sepolia",
        }

        for key, value in chain_mapping.items():
            if key in src:
                return value

        return default

    def _extract_cctp_parameters(self, msg_lower: str) -> Dict[str, Any]:
        """Extracts CCTP transfer parameters from the message."""
        # Simple heuristic regex for extraction (simulating an LLM tool call parameter extraction)
        amount_match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        amount = float(amount_match.group(1)) if amount_match else 100.0

        source_chain_match = re.search(r"from\s+(\w+)", msg_lower)
        source_chain = self._resolve_chain(source_chain_match, "ethereum_sepolia")

        # We assume a fixed target chain logic for the dummy regex, but in a real LLM we'd parse "to [chain]"
        target_chain_match = re.search(r"to\s+(\w+)", msg_lower)
        target_chain = self._resolve_chain(target_chain_match, "arbitrum_sepolia")

        return {
            "amount": amount,
            "source_chain": source_chain,
            "target_chain": target_chain,
            "destination_address": "0x1234567890abcdef1234567890abcdef12345678",
        }

    def _match_intent(self, msg_lower: str) -> str:
        """Helper to match the intent from a lowercased message."""
        intent_mapping = {
            "STATUS": ["status", "how are we doing", "summary", "update"],
            "PAUSE": ["pause", "stop trading", "halt"],
            "RESUME": ["resume", "start trading", "unpause"],
            "KILL_SWITCH": ["kill switch", "emergency", "shut it down", "panic"],
        }

        for intent, keywords in intent_mapping.items():
            if any(keyword in msg_lower for keyword in keywords):
                return intent

        return "UNKNOWN"

    async def parse_intent(
        self, user_message: str
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Queries an LLM API to parse natural language into engine commands.
        Valid intents: STATUS, PAUSE, RESUME, KILL_SWITCH, CCTP_TRANSFER, UNKNOWN

        Returns a tuple: (intent_string, optional_tool_arguments_dict)
        """
        logger.debug(f"Parsing intent for: '{user_message}'")

        # Simulate an API call to an LLM with tool calling enabled
        await asyncio.sleep(1.0)

        msg_lower = user_message.lower()

        # Dummy NLP / Tool Calling Logic
        if "bridge" in msg_lower or "cctp" in msg_lower or "move usdc" in msg_lower:
            logger.info(
                "Copilot identified CCTP Transfer intent. Extracting parameters..."
            )

            tool_args = self._extract_cctp_parameters(msg_lower)
            logger.debug(f"Extracted tool args: {tool_args}")
            return "CCTP_TRANSFER", tool_args

        return self._match_intent(msg_lower), None
