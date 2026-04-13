"""GLM AI 分析模块 — 自然语言查询数据 + AI 分析"""

import json
import logging

from openai import AsyncOpenAI

from bot.config import settings
from bot.database import async_session
from bot import queries

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是 MIC 音乐教育机构的数据分析顾问。你的灵魂来自一位拥有极高智慧、极度理性的投资大师和思想家。你用这种思维方式来分析教育机构的运营数据。

【人格内核】
你交流风格直接、犀利、充满常识，偶尔带有毒舌和幽默感。你不提供空洞的安慰，而是传授如何通过理智、自律和持续改进来让机构运营得更好。

【核心思维模式】
- 逆向思维：不只看"如何增长"，更关注"什么会导致衰退"——然后坚决避免这些事
- 能力圈：对超出数据范围的问题坦承"我不知道"，绝不胡说八道
- 跨学科思维：用复利、安全边际、激励机制等基本原理分析业务
- 警惕心理陷阱：警惕从众、自怜、确认偏误等人性弱点在业务决策中的影响

【分析准则】
- 追求常识：好的运营不需要花哨的技巧，而是避开蠢事、做好基本功课
- 极度重视数据质量：没有数据支撑的判断都是猜测
- 关注长期价值：签约金额重要，但学生满意度和口碑才是真正的"护城河"
- 痛恨自欺欺人：数据不好就说不好，粉饰太平是最大的愚蠢

【回复风格】
- 语言精炼、直击本质，多用生活中的比喻和常识
- 当数据暴露问题时，毫不留情地指出；但目的是引导改进，而非打击
- 该夸就夸，该骂就骂，绝不和稀泥
- 用中文回复

你会收到两部分内容：
1. 用户的原始问题
2. 从数据库查到的相关数据（JSON）

请根据数据回答用户的问题，风格鲜明但不失专业。如果数据不足，直接说缺什么。"""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.GLM_API_KEY,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )


async def _gather_context(message: str) -> str:
    """根据用户消息提取数据上下文"""
    import re
    context_parts = []
    name_found = False

    async with async_session() as session:
        # 始终带上日报数据作为背景
        report = await queries.daily_report(session)
        context_parts.append(f"【当前日报数据】\n{json.dumps(report, ensure_ascii=False, default=str)}")

        # 提取人名搜索（中文姓名 2-4 字）→ 跟 /s 命令同款流程
        names = re.findall(r"[\u4e00-\u9fff]{2,4}", message)
        for name in names:
            result = await queries.search_student(session, name)
            if result:
                context_parts.append(f"【学生数据: {name}】\n{json.dumps(result, ensure_ascii=False, default=str)}")
                name_found = True
                break  # 命中一个就够了，避免数据过载

        # 以下只在未命中人名时补充
        if not name_found:
            if any(kw in message for kw in ["排行", "排名", "销售", "业绩", "签约"]):
                rank = await queries.sales_rank(session)
                context_parts.append(f"【本月销售排行】\n{json.dumps(rank, ensure_ascii=False)}")

            if any(kw in message for kw in ["趋势", "走势", "最近", "这几天", "这周"]):
                trend = await queries.trend_7days(session)
                context_parts.append(f"【近7天趋势】\n{json.dumps(trend, ensure_ascii=False, default=str)}")

            if any(kw in message for kw in ["跟进", "日志", "跟踪", "回访", "作品集", "作品", "进度"]):
                status = await queries.signed_students_status(session)
                context_parts.append(f"【学生跟进&作品集概览】\n{json.dumps(status, ensure_ascii=False, default=str)[:4000]}")

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
