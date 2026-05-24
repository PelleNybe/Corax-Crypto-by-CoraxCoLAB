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

        if regime == "TRENDING_UP":
            synthesis = (
                "Copilot: Bullish momentum confirmed. Order flow supports continuation."
            )
        elif regime == "VOLATILE_CRASH":
            synthesis = "Copilot: Extreme downside volatility. Risk-off mode activated."
        elif regime == "RANGING":
            synthesis = (
                "Copilot: Market consolidating. Avoiding chop until volume expands."
            )
        else:
            synthesis = "Copilot: Analyzing micro-structure for clear direction..."

        self._cached_synthesis = synthesis
        self._last_state_hash = state_hash
        return synthesis

    def _extract_cctp_parameters(self, msg_lower: str) -> Dict[str, Any]:
        """Extracts CCTP transfer parameters from the message."""
        # Simple heuristic regex for extraction (simulating an LLM tool call parameter extraction)
        amount_match = re.search(r"(\d+(\.\d+)?)", msg_lower)
        amount = float(amount_match.group(1)) if amount_match else 100.0

        source_chain_match = re.search(r"from\s+(\w+)", msg_lower)
        source_chain = "ethereum_sepolia"
        if source_chain_match:
            src = source_chain_match.group(1).lower()
            if "optimism" in src:
                source_chain = "optimism_sepolia"
            elif "avalanche" in src:
                source_chain = "avalanche_fuji"
            elif "arbitrum" in src:
                source_chain = "arbitrum_sepolia"
            elif "solana" in src:
                source_chain = "solana_devnet"
            elif "base" in src:
                source_chain = "base_sepolia"
            elif "polygon" in src:
                source_chain = "polygon_amoy"
            elif "ethereum" in src:
                source_chain = "ethereum_sepolia"

        # We assume a fixed target chain logic for the dummy regex, but in a real LLM we'd parse "to [chain]"
        target_chain_match = re.search(r"to\s+(\w+)", msg_lower)
        target_chain = "arbitrum_sepolia"
        if target_chain_match:
            tgt = target_chain_match.group(1).lower()
            if "ethereum" in tgt:
                target_chain = "ethereum_sepolia"
            elif "optimism" in tgt:
                target_chain = "optimism_sepolia"
            elif "avalanche" in tgt:
                target_chain = "avalanche_fuji"
            elif "arbitrum" in tgt:
                target_chain = "arbitrum_sepolia"
            elif "solana" in tgt:
                target_chain = "solana_devnet"
            elif "base" in tgt:
                target_chain = "base_sepolia"
            elif "polygon" in tgt:
                target_chain = "polygon_amoy"

        return {
            "amount": amount,
            "source_chain": source_chain,
            "target_chain": target_chain,
            "destination_address": "0x1234567890abcdef1234567890abcdef12345678",
        }

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

        if (
            "status" in msg_lower
            or "how are we doing" in msg_lower
            or "summary" in msg_lower
            or "update" in msg_lower
        ):
            return "STATUS", None
        elif "pause" in msg_lower or "stop trading" in msg_lower or "halt" in msg_lower:
            return "PAUSE", None
        elif (
            "resume" in msg_lower
            or "start trading" in msg_lower
            or "unpause" in msg_lower
        ):
            return "RESUME", None
        elif (
            "kill switch" in msg_lower
            or "emergency" in msg_lower
            or "shut it down" in msg_lower
            or "panic" in msg_lower
        ):
            return "KILL_SWITCH", None

        return "UNKNOWN", None
