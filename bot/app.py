"""FastAPI + Telegram Bot 启动入口"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telegram.ext import ApplicationBuilder, CommandHandler

from bot.config import settings
from bot.handlers import start_cmd, help_cmd, report_cmd, search_cmd, rank_cmd, portfolio_cmd, trend_cmd
from bot.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 全局引用
bot_app = None
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — 启动/关闭 Bot 和定时任务"""
    global bot_app, scheduler

    # ── 启动 Telegram Bot (polling) ──
    bot_app = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    bot_app.add_handler(CommandHandler("start", start_cmd))
    bot_app.add_handler(CommandHandler("r", report_cmd))
    bot_app.add_handler(CommandHandler("s", search_cmd))
    bot_app.add_handler(CommandHandler("k", rank_cmd))
    bot_app.add_handler(CommandHandler("p", portfolio_cmd))
    bot_app.add_handler(CommandHandler("t", trend_cmd))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram Bot 已启动 (polling)")

    # ── 启动定时任务 ──
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("APScheduler 已启动")

    yield

    # ── 关闭 ──
    if scheduler:
        scheduler.shutdown(wait=False)
    if bot_app:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    logger.info("Bot 已关闭")


app = FastAPI(title="MIC Data Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.app:app", host="0.0.0.0", port=8010, reload=False)
