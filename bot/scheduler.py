"""定时任务 — 每天 18:00 发送日报"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

from bot.config import settings
from bot.database import async_session
from bot import queries, formatters

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def send_daily_report():
    """发送每日数据播报"""
    chat_id = settings.report_chat_id
    if not chat_id:
        logger.warning("REPORT_CHAT_ID 未配置，跳过日报")
        return

    try:
        async with async_session() as session:
            data = await queries.daily_report(session)
        text = formatters.format_report(data)

        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info("日报已发送至 chat_id=%s", chat_id)
    except Exception:
        logger.exception("日报发送失败")


async def send_today_updates():
    """发送今日动态（有数据才发）"""
    chat_id = settings.report_chat_id
    if not chat_id:
        return

    try:
        async with async_session() as session:
            data = await queries.today_updates(session)
        text = formatters.format_today_updates(data)
        if text:
            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            await bot.send_message(chat_id=chat_id, text=text)
            logger.info("今日动态已发送至 chat_id=%s", chat_id)
    except Exception:
        logger.exception("今日动态发送失败")


def setup_scheduler():
    """注册定时任务"""
    scheduler.add_job(
        send_daily_report,
        "cron",
        hour=18,
        minute=0,
        id="daily_report",
        replace_existing=True,
    )
    logger.info("定时任务已注册：每天 18:00 发送日报")

    scheduler.add_job(
        send_today_updates,
        "cron",
        hour=17,
        minute=50,
        id="today_updates",
        replace_existing=True,
    )
    logger.info("定时任务已注册：每天 17:50 发送今日动态")
    return scheduler
