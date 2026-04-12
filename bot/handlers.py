"""Telegram 命令处理"""

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import settings
from bot.database import async_session
from bot import queries, formatters


# ────────────────────────── 权限校验 ──────────────────────────

def _is_allowed(update: Update) -> bool:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return False
    allowed = settings.allowed_chat_ids
    return not allowed or chat_id in allowed


# ────────────────────────── 命令 ──────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "🤖 MIC 数据播报 Bot\n\n"
        "/r — 今日/月度数据报告\n"
        "/s 姓名 — 搜索学生\n"
        "/k — 本月销售排行\n"
        "/p 姓名 — 作品集\n"
        "/t — 近7天趋势"
    )


help_cmd = start_cmd


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    try:
        async with async_session() as session:
            data = await queries.daily_report(session)
        await update.message.reply_text(formatters.format_report(data))
    except Exception as e:
        await update.message.reply_text(f"⚠️ 数据查询异常，请稍后重试\n({e})")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/s 姓名")
        return
    name = " ".join(context.args)
    try:
        async with async_session() as session:
            data = await queries.search_student(session, name)
        if data is None:
            await update.message.reply_text("❌ 未找到该学生")
        else:
            await update.message.reply_text(formatters.format_search(data))
    except Exception as e:
        await update.message.reply_text(f"⚠️ 数据查询异常，请稍后重试\n({e})")


async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    try:
        async with async_session() as session:
            data = await queries.sales_rank(session)
        await update.message.reply_text(formatters.format_rank(data))
    except Exception as e:
        await update.message.reply_text(f"⚠️ 数据查询异常，请稍后重试\n({e})")


async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/p 姓名")
        return
    name = " ".join(context.args)
    try:
        async with async_session() as session:
            data = await queries.portfolio_by_name(session, name)
        if data is None:
            await update.message.reply_text("❌ 未找到该学生")
        else:
            await update.message.reply_text(formatters.format_portfolios(data))
    except Exception as e:
        await update.message.reply_text(f"⚠️ 数据查询异常，请稍后重试\n({e})")


async def trend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    try:
        async with async_session() as session:
            data = await queries.trend_7days(session)
        await update.message.reply_text(formatters.format_trend(data))
    except Exception as e:
        await update.message.reply_text(f"⚠️ 数据查询异常，请稍后重试\n({e})")


async def ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自然语言消息 → AI 分析"""
    if not _is_allowed(update):
        return
    text = update.message.text
    if not text or text.startswith("/"):
        return

    await update.message.reply_text("思考中...")
    try:
        from bot.ai import ask_glm
        reply = await ask_glm(text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"⚠️ AI 分析失败\n({e})")
