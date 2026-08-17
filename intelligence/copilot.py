import json
import aiohttp
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
        self.api_url = "https://api.openai.com/v1/chat/completions"

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

        logger.debug("Generating synthesis via LLM Copilot...")

        system_prompt = (
            "You are Corax Copilot, an AI assistant for a high-frequency trading engine. "
            "Given the current market regime and recent actions, provide a brief, one-sentence "
            "market synthesis for the human operator."
        )

        user_prompt = f"Current Regime: {regime}\nRecent Action: {recent_action}"

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 60,
                    "temperature": 0.7,
                }

                async with session.post(
                    self.api_url, headers=headers, json=payload, timeout=5
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        synthesis = data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.warning(
                            f"LLM API returned status {response.status}. Falling back to default synthesis."
                        )
                        synthesis = self._get_fallback_synthesis(regime)
        except Exception as e:
            logger.error(f"Failed to generate LLM synthesis: {e}. Falling back.")
            synthesis = self._get_fallback_synthesis(regime)

        self._cached_synthesis = synthesis
        self._last_state_hash = state_hash
        return synthesis

    def _get_fallback_synthesis(self, regime: str) -> str:
        regime_messages = {
            "TRENDING_UP": "Copilot: Bullish momentum confirmed. Order flow supports continuation.",
            "VOLATILE_CRASH": "Copilot: Extreme downside volatility. Risk-off mode activated.",
            "RANGING": "Copilot: Market consolidating. Avoiding chop until volume expands.",
        }

        return regime_messages.get(
            regime, "Copilot: Analyzing micro-structure for clear direction..."
        )

    def _match_intent_fallback(self, msg_lower: str) -> str:
        """Helper to match the intent from a lowercased message if LLM fails."""
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

        system_prompt = (
            "You are Corax Copilot, an AI command center for an algorithmic trading engine. "
            "Analyze the user's message and determine the correct intent. "
            "Available intents are: STATUS, PAUSE, RESUME, KILL_SWITCH, CCTP_TRANSFER, UNKNOWN. "
            "If the user wants to bridge or move USDC between chains, you MUST invoke the `execute_cctp_transfer` tool. "
            "Otherwise, respond with exactly ONE of the intent strings above and nothing else."
        )

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "tools": self.get_tool_schemas(),
                    "tool_choice": "auto",
                    "temperature": 0.0,
                }

                async with session.post(
                    self.api_url, headers=headers, json=payload, timeout=5
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        message = data["choices"][0]["message"]

                        if message.get("tool_calls"):
                            tool_call = message["tool_calls"][0]
                            if tool_call["function"]["name"] == "execute_cctp_transfer":
                                tool_args = json.loads(
                                    tool_call["function"]["arguments"]
                                )
                                logger.info(
                                    "Copilot identified CCTP Transfer intent from LLM tool call."
                                )
                                return "CCTP_TRANSFER", tool_args

                        content = message.get("content", "").strip().upper()
                        valid_intents = [
                            "STATUS",
                            "PAUSE",
                            "RESUME",
                            "KILL_SWITCH",
                            "UNKNOWN",
                        ]
                        if content in valid_intents:
                            return content, None

                    else:
                        logger.warning(
                            f"LLM intent parsing failed with status {response.status}. Using fallback."
                        )
        except Exception as e:
            logger.error(f"Error parsing intent via LLM: {e}. Using fallback.")

        # Fallback to local heuristic matching
        msg_lower = user_message.lower()
        return self._match_intent_fallback(msg_lower), None
