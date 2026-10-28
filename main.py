import time
import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

import config
from bot.handlers import (
    start_handler,
    callback_handler,
    message_handler,
    login_handler,
    userbot_handler,
    logout_userbot_handler,
    cancel_handler
)
from bot.scheduler import WinGoScheduler
from services.userbot_manager import userbot_manager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("WinGoBot")

scheduler_instance = None

async def post_init(application: Application):
    """Called after application is initialized, starts background scheduler and userbot"""
    global scheduler_instance
    scheduler_instance = WinGoScheduler(application.bot)
    await scheduler_instance.start()
    logger.info("✅ WinGo Multi-Game Scheduler started successfully!")

    # Auto-start Telegram Userbot if session is configured
    try:
        started = await userbot_manager.start()
        if started:
            logger.info("✅ Telegram Userbot client initialized for animated emojis!")
    except Exception as ue:
        logger.warning(f"⚠️ Userbot auto-start notice: {ue}")

async def post_shutdown(application: Application):
    """Called during graceful shutdown"""
    global scheduler_instance
    if scheduler_instance:
        await scheduler_instance.stop()
    try:
        await userbot_manager.stop()
    except Exception:
        pass
    logger.info("🛑 Bot shutdown complete.")

def main():
    if not config.BOT_TOKEN:
        logger.critical("❌ BOT_TOKEN is missing! Please configure it in .env file.")
        return

    logger.info("🚀 Starting Modern WinGo VIP Prediction Bot...")
    logger.info(f"👑 Admins configured: {config.ADMIN_IDS}")
    logger.info("⚡ Games: WinGo 30s, 1M, 3M, 5M (Multi-Channel)")
    logger.info("🎨 UI: Separate Messages, Styled High-Impact Buttons, AI Prediction")

    # Resilient Telegram Network Configuration (prevents ConnectTimeout / TimedOut on VPS)
    # read_timeout (40s) must strictly exceed get_updates timeout (20s)
    request_config = HTTPXRequest(
        connection_pool_size=30,
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=25.0,
        pool_timeout=20.0
    )

    async def error_handler(update: object, context):
        logger.error(f"⚠️ Telegram update error: {context.error}", exc_info=context.error)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .request(request_config)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_error_handler(error_handler)

    # Register handlers
    app.add_handler(CommandHandler(["start", "admin"], start_handler))
    app.add_handler(CommandHandler("login", login_handler))
    app.add_handler(CommandHandler("userbot", userbot_handler))
    app.add_handler(CommandHandler("logout_userbot", logout_userbot_handler))
    app.add_handler(CommandHandler("cancel", cancel_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL | filters.Sticker.ALL) & ~filters.COMMAND, message_handler))

    # Resilient polling loop with bootstrap retries
    while True:
        try:
            app.run_polling(
                drop_pending_updates=False,
                bootstrap_retries=5,
                timeout=20,
                poll_interval=0.5
            )
            break
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            logger.error(f"Polling loop network error: {e}. Reconnecting in 3s...", exc_info=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
