"""GLM AI 分析模块 — 自然语言查询数据 + AI 分析"""

import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.database import async_session
from bot import queries

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 MIC 音乐教育机构的 CRM 数据分析助手。用户会用自然语言问关于学生、销售、作品集等数据的问题。

你会收到两部分内容：
1. 用户的原始问题
2. 从数据库查到的相关数据（JSON）

请根据数据回答用户的问题。要求：
- 用中文回复
- 简洁专业
- 如果数据不足，说明缺少什么信息
- 可以给出建议和分析，不只是罗列数据"""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.GLM_API_KEY,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )


async def _gather_context(message: str) -> str:
    """根据用户消息提取数据上下文"""
    context_parts = []
    async with async_session() as session:
        # 始终带上日报数据作为背景
        report = await queries.daily_report(session)
        context_parts.append(f"【当前日报数据】\n{json.dumps(report, ensure_ascii=False, default=str)}")

        # 尝试提取人名搜索（中文姓名 2-4 字）
        import re
        names = re.findall(r"[\u4e00-\u9fff]{2,4}", message)
        for name in names:
            result = await queries.search_student(session, name)
            if result:
                context_parts.append(f"【搜索: {name}】\n{json.dumps(result, ensure_ascii=False, default=str)[:2000]}")

        # 如果问题涉及排行
        if any(kw in message for kw in ["排行", "排名", "销售", "业绩", "签约"]):
            rank = await queries.sales_rank(session)
            context_parts.append(f"【本月销售排行】\n{json.dumps(rank, ensure_ascii=False)}")

        # 如果问题涉及趋势
        if any(kw in message for kw in ["趋势", "走势", "最近", "这几天", "这周"]):
            trend = await queries.trend_7days(session)
            context_parts.append(f"【近7天趋势】\n{json.dumps(trend, ensure_ascii=False, default=str)}")

    return "\n\n".join(context_parts)


async def ask_glm(message: str) -> str:
    """用 GLM 分析用户问题并返回回复"""
    if not settings.GLM_API_KEY:
        return "AI 功能未配置（缺少 GLM_API_KEY）"

    try:
        context = await _gather_context(message)
        client = _get_client()

        response = await client.chat.completions.create(
            model="glm-4-flash",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"问题：{message}\n\n相关数据：\n{context}"},
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.exception("GLM API 调用失败")
        return f"AI 分析失败：{e}"
