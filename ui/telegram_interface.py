from loguru import logger
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

from core.config import settings
from intelligence.copilot import CoraxCopilot
from core.state import global_state


class CoraxTelegramInterface:
    """
    Omni-Channel Command Center using Telegram.
    Leverages CoraxCopilot to parse natural language intents instead of rigid slash commands.
    """

    def __init__(self, engine):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.engine = engine
        self.copilot = CoraxCopilot()
        self.bot = None
        self.dp = None

        if self.token:
            self.bot = Bot(token=self.token)
            self.dp = Dispatcher()
            self._register_handlers()
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram interface disabled.")

    def _register_handlers(self):
        @self.dp.message(CommandStart())
        async def send_welcome(message: types.Message):
            await message.reply(
                "Corax Crypto Omni-Channel Command Center online.\n"
                "You can speak to me naturally. E.g., 'What is the current status?', 'Pause trading', 'Hit the kill switch', 'Bridge 100 USDC to Arbitrum'."
            )

        @self.dp.message()
        async def handle_message(message: types.Message):
            user_text = message.text
            logger.info(f"Received Telegram message: {user_text}")

            # Send processing indicator
            processing_msg = await message.reply(
                "Processing intent via CoraxCopilot..."
            )

            try:
                # Ask LLM Copilot to parse the intent
                intent, tool_args = await self.copilot.parse_intent(user_text)
                logger.info(f"Parsed Intent: {intent}")

                response_text = "Action executed."

                if intent == "STATUS":
                    summary = global_state.get_summary()
                    synthesis = global_state.synthesis

                    response_text = (
                        f"📊 **Corax Global State Summary**\n\n"
                        f"Balance: ${summary.get('balance', 0):,.2f}\n"
                        f"Regime: {summary.get('regime', 'UNKNOWN')}\n"
                        f"Last Action: {summary.get('recent_action', 'None')}\n\n"
                        f"🧠 **Copilot Synthesis**:\n{synthesis}"
                    )
                elif intent == "PAUSE":
                    self.engine.is_paused = True
                    response_text = (
                        "⏸️ **Trading Engine Paused.** No new orders will be executed."
                    )
                elif intent == "RESUME":
                    self.engine.is_paused = False
                    response_text = (
                        "▶️ **Trading Engine Resumed.** Resuming normal operations."
                    )
                elif intent == "KILL_SWITCH":
                    self.engine.risk_manager.kill_switch_active = True
                    response_text = "🛑 **KILL SWITCH ACTIVATED.** All further BUY signals are blocked."
                elif intent == "CCTP_TRANSFER":
                    if tool_args:
                        response_text = f"🌉 **CCTP Transfer Initiated.** Queuing {tool_args['amount']} USDC from {tool_args['source_chain']} to {tool_args['target_chain']}."
                        await self.engine.order_manager.execute_cctp_transfer(
                            amount=tool_args["amount"],
                            source_chain=tool_args["source_chain"],
                            target_chain=tool_args["target_chain"],
                            destination_address=tool_args["destination_address"],
                        )
                    else:
                        response_text = (
                            "❌ Failed to extract parameters for CCTP transfer."
                        )
                else:
                    response_text = "I'm sorry, I didn't understand that command. Try asking for status, pausing, resuming, bridge operations, or the kill switch."

                await self.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id,
                    text=response_text,
                    parse_mode="Markdown",
                )

            except Exception as e:
                logger.error(f"Error handling Telegram message: {e}")
                await self.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id,
                    text="❌ Error processing request.",
                )

    async def start_polling(self):
        """Starts the Telegram bot polling loop with automatic reconnect."""
        if not self.bot or not self.dp:
            return

        import asyncio

        logger.info("Starting Telegram Bot Polling...")
        while True:
            try:
                await self.dp.start_polling(self.bot, drop_pending_updates=True)
            except Exception as e:
                logger.error(
                    f"Telegram polling error: {e}. Reconnecting in 5 seconds..."
                )
                await asyncio.sleep(5)

    async def stop(self):
        if self.bot:
            await self.bot.session.close()
