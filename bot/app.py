"""FastAPI + Telegram Bot 启动入口"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from telegram.ext import ApplicationBuilder, CommandHandler

from bot.config import settings
from bot.database import async_session
from telegram.ext import MessageHandler, filters

from bot.handlers import start_cmd, help_cmd, report_cmd, search_cmd, rank_cmd, portfolio_cmd, trend_cmd, today_cmd, ai_message
from bot.scheduler import setup_scheduler
from bot import queries, formatters

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
    bot_app.add_handler(CommandHandler("d", today_cmd))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_message))

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


# ────────────────────────── REST API ──────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/report")
async def api_report():
    """今日/月度数据报告"""
    try:
        async with async_session() as session:
            data = await queries.daily_report(session)
        return data
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/search")
async def api_search(name: str = Query(..., description="学生姓名")):
    """搜索学生信息 + 跟进记录 + 作品集"""
    try:
        async with async_session() as session:
            data = await queries.search_student(session, name)
        if data is None:
            return JSONResponse(status_code=404, content={"error": "未找到该学生"})
        return data
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/rank")
async def api_rank():
    """本月销售排行"""
    try:
        async with async_session() as session:
            data = await queries.sales_rank(session)
        return {"rank": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/portfolio")
async def api_portfolio(name: str = Query(..., description="学生姓名")):
    """按姓名查作品集"""
    try:
        async with async_session() as session:
            data = await queries.portfolio_by_name(session, name)
        if data is None:
            return JSONResponse(status_code=404, content={"error": "未找到该学生"})
        return {"results": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/trend")
async def api_trend():
    """近7天趋势"""
    try:
        async with async_session() as session:
            data = await queries.trend_7days(session)
        return {"trend": data}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/today")
async def api_today():
    """今日跟进日志 + 作品集动态"""
    try:
        async with async_session() as session:
            data = await queries.today_updates(session)
        return data
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ────────────────────────── 入口 ──────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.app:app", host="0.0.0.0", port=8010, reload=False)
