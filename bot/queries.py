"""只读数据库查询 — 所有查询通过 raw SQLAlchemy core 执行，不依赖 ORM model"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ────────────────────────── 工具函数 ──────────────────────────

def _today() -> date:
    return date.today()


def _month_start() -> date:
    today = _today()
    return today.replace(day=1)


def _parse_amount(raw: str | None) -> float:
    """尝试从字符串解析金额，兼容各种格式"""
    if not raw:
        return 0.0
    cleaned = raw.replace(",", "").replace("，", "").replace("¥", "").replace("￥", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _is_signed(row: dict) -> bool:
    """判断 crm_leads 行是否已签约：signing_date+signing_amount 或 consultation_stage 含签约"""
    sd = row.get("signing_date")
    sa = row.get("signing_amount")
    has_signing = bool(sd and str(sd).strip()) and bool(sa and str(sa).strip() and str(sa).strip() != "0")
    stage = str(row.get("consultation_stage") or "").strip()
    has_stage = "签约" in stage
    return has_signing or has_stage


def _parse_date(date_str: str | None) -> date | None:
    """解析 String 日期，兼容 YYYY/MM/DD 和 YYYY-MM-DD"""
    if not date_str:
        return None
    s = str(date_str).strip()[:10]
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        pass
    try:
        return date.fromisoformat(s.replace("/", "-"))
    except (ValueError, TypeError):
        return None


def _date_match(date_str: str | None, target: date) -> bool:
    parsed = _parse_date(date_str)
    return parsed == target if parsed else False


def _date_in_month(date_str: str | None, start: date, end: date) -> bool:
    parsed = _parse_date(date_str)
    return start <= parsed <= end if parsed else False


async def _fetch_leads(session: AsyncSession) -> list[dict]:
    """获取所有 crm_leads 记录"""
    result = await session.execute(
        text("SELECT * FROM crm_leads ORDER BY id")
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _fetch_action_logs(session: AsyncSession, user_id: int, limit: int = 2) -> list[dict]:
    """获取指定 user_id 的跟进日志"""
    result = await session.execute(
        text("SELECT * FROM action_logs WHERE user_id = :uid ORDER BY created_at DESC LIMIT :lim"),
        {"uid": user_id, "lim": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _fetch_portfolios(session: AsyncSession, user_id: int) -> list[dict]:
    """获取指定 user_id 的作品集"""
    result = await session.execute(
        text("SELECT * FROM portfolios WHERE user_id = :uid ORDER BY created_at DESC"),
        {"uid": user_id},
    )
    return [dict(row._mapping) for row in result.fetchall()]


# ────────────────────────── 业务查询 ──────────────────────────

async def daily_report(session: AsyncSession) -> dict[str, Any]:
    """日报/月报数据"""
    leads = await _fetch_leads(session)
    today = _today()
    month_start = _month_start()
    today_str = today.isoformat()

    sales_map: dict[str, dict] = {}

    for row in leads:
        person = row.get("responsible_person") or "未分配"
        if person not in sales_map:
            sales_map[person] = {"today_referrals": 0, "today_contracts": 0, "today_amount": 0.0,
                                 "month_referrals": 0, "month_contracts": 0, "month_amount": 0.0}

        sm = sales_map[person]

        # 推荐统计
        ref_date = row.get("referral_date")
        if _date_match(ref_date, today):
            sm["today_referrals"] += 1
        if _date_in_month(ref_date, month_start, today):
            sm["month_referrals"] += 1

        # 签约统计
        if _is_signed(row):
            sign_date = row.get("signing_date")
            amount = _parse_amount(row.get("signing_amount"))
            if _date_match(sign_date, today):
                sm["today_contracts"] += 1
                sm["today_amount"] += amount
            if _date_in_month(sign_date, month_start, today):
                sm["month_contracts"] += 1
                sm["month_amount"] += amount

    total_today_ref = sum(s["today_referrals"] for s in sales_map.values())
    total_today_con = sum(s["today_contracts"] for s in sales_map.values())
    total_today_amt = sum(s["today_amount"] for s in sales_map.values())
    total_month_ref = sum(s["month_referrals"] for s in sales_map.values())
    total_month_con = sum(s["month_contracts"] for s in sales_map.values())
    total_month_amt = sum(s["month_amount"] for s in sales_map.values())

    return {
        "today": {"referrals": total_today_ref, "contracts": total_today_con, "amount": total_today_amt},
        "month": {"referrals": total_month_ref, "contracts": total_month_con, "amount": total_month_amt},
        "sales": sales_map,
        "date": today_str,
    }


async def search_student(session: AsyncSession, name: str) -> dict | None:
    """搜索学生 → 基本信息 + 最近跟进 + 作品集"""
    # 先在 crm_leads 中模糊搜索
    result = await session.execute(
        text("SELECT * FROM crm_leads WHERE user_name ILIKE :name LIMIT 5"),
        {"name": f"%{name}%"},
    )
    leads = [dict(row._mapping) for row in result.fetchall()]

    if not leads:
        # 尝试在 users 表搜索
        result2 = await session.execute(
            text("SELECT * FROM users WHERE real_name ILIKE :name AND role = 'STUDENT' LIMIT 5"),
            {"name": f"%{name}%"},
        )
        users = [dict(row._mapping) for row in result2.fetchall()]
        if not users:
            return None
        # 用 users 数据构建结果
        results = []
        for u in users:
            uid = u["id"]
            logs = await _fetch_action_logs(session, uid)
            portfolios = await _fetch_portfolios(session, uid)
            results.append({"source": "users", "info": u, "logs": logs, "portfolios": portfolios})
        return {"results": results}

    results = []
    for lead in leads:
        lead_id = lead.get("id")
        logs = await _fetch_action_logs(session, lead_id)
        portfolios = await _fetch_portfolios(session, lead_id)
        results.append({"source": "crm_leads", "info": lead, "logs": logs, "portfolios": portfolios})

    return {"results": results}


async def sales_rank(session: AsyncSession) -> list[dict]:
    """本月销售排行"""
    leads = await _fetch_leads(session)
    today = _today()
    month_start = _month_start()

    rank_map: dict[str, dict] = {}
    for row in leads:
        if not _is_signed(row):
            continue
        sign_date = row.get("signing_date")
        if not _date_in_month(sign_date, month_start, today):
            continue
        person = row.get("responsible_person") or "未分配"
        if person not in rank_map:
            rank_map[person] = {"name": person, "contracts": 0, "amount": 0.0}
        rank_map[person]["contracts"] += 1
        rank_map[person]["amount"] += _parse_amount(row.get("signing_amount"))

    ranked = sorted(rank_map.values(), key=lambda x: x["amount"], reverse=True)
    return ranked


async def portfolio_by_name(session: AsyncSession, name: str) -> list[dict] | None:
    """按姓名查作品集"""
    # crm_leads 查找
    result = await session.execute(
        text("SELECT user_id, user_name FROM crm_leads WHERE user_name ILIKE :name"),
        {"name": f"%{name}%"},
    )
    matches = [dict(row._mapping) for row in result.fetchall()]

    if not matches:
        # 尝试 users 表
        result2 = await session.execute(
            text("SELECT id, real_name FROM users WHERE real_name ILIKE :name AND role = 'STUDENT'"),
            {"name": f"%{name}%"},
        )
        matches = [{"user_id": row[0], "user_name": row[1]} for row in result2.fetchall()]

    if not matches:
        return None

    results = []
    for m in matches:
        uid = m.get("user_id") or m.get("id")
        if uid:
            portfolios = await _fetch_portfolios(session, uid)
            results.append({"name": m.get("user_name") or m.get("real_name"), "portfolios": portfolios})

    return results


async def signed_students_status(session: AsyncSession, person: str | None = None) -> list[dict]:
    """学生的跟进日志 + 作品集概览，可按负责人筛选（模糊匹配），包含签约和未签约"""
    leads = await _fetch_leads(session)
    results = []
    for lead in leads:
        if person and person not in (lead.get("responsible_person") or ""):
            continue
        lead_id = lead["id"]
        logs = await _fetch_action_logs(session, lead_id, limit=3)
        portfolios = await _fetch_portfolios(session, lead_id)
        results.append({
            "name": lead.get("user_name"),
            "signing_date": lead.get("signing_date"),
            "signing_amount": lead.get("signing_amount"),
            "responsible_person": lead.get("responsible_person"),
            "recent_logs": [
                {"note": log.get("note"), "log_type": log.get("log_type"), "log_date": str(log.get("log_date", ""))}
                for log in logs
            ],
            "portfolio_count": len(portfolios),
            "portfolios": [
                {"title": p.get("title"), "work_type": p.get("work_type"), "review_status": p.get("review_status"), "deadline": str(p.get("deadline", ""))}
                for p in portfolios[:5]
            ],
        })
    return results


async def trend_7days(session: AsyncSession) -> list[dict]:
    """近7天每日趋势"""
    leads = await _fetch_leads(session)
    today = _today()
    days = []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        referrals = 0
        contracts = 0
        amount = 0.0

        for row in leads:
            ref_date = row.get("referral_date")
            if _date_match(ref_date, d):
                referrals += 1
            if _is_signed(row):
                sign_date = row.get("signing_date")
                if _date_match(sign_date, d):
                    contracts += 1
                    amount += _parse_amount(row.get("signing_amount"))

        days.append({"date": d, "referrals": referrals, "contracts": contracts, "amount": amount})

    return days
