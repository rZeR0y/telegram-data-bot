"""消息格式化 — 将查询结果格式化为 Telegram 文本"""

from datetime import date
from typing import Any


def fmt_amount(amount: float) -> str:
    return f"¥{amount:,.0f}"


def fmt_date_short(d: date) -> str:
    return d.strftime("%m-%d")


def format_report(data: dict[str, Any]) -> str:
    """格式化日报/月报"""
    today = data["date"]
    t = data["today"]
    m = data["month"]
    sales = data["sales"]

    lines = [
        f"📊 {today} 数据日报",
        "",
        f"▸ 今日推荐：{t['referrals']}人",
        f"▸ 今日签约：{t['contracts']}人（{fmt_amount(t['amount'])}）",
        f"▸ 本月累计推荐：{m['referrals']}人",
        f"▸ 本月累计签约：{m['contracts']}人（{fmt_amount(m['amount'])}）",
    ]

    if sales:
        lines.append("")
        lines.append("👥 销售明细：")
        for person, sm in sorted(sales.items(), key=lambda x: x[1]["month_referrals"], reverse=True):
            if sm["month_referrals"] == 0 and sm["month_contracts"] == 0:
                continue
            lines.append(
                f"  {person}  — "
                f"推荐 {sm['month_referrals']} | "
                f"签约 {sm['month_contracts']}（{fmt_amount(sm['month_amount'])}）"
            )

    return "\n".join(lines)


def format_search(data: dict) -> str:
    """格式化搜索结果"""
    results = data.get("results", [])
    if not results:
        return "❌ 未找到该学生"

    parts = []
    for r in results:
        info = r["info"]
        source = r["source"]

        if source == "crm_leads":
            name = info.get("user_name", "未知")
            stage = info.get("consultation_stage") or info.get("signing_intention") or "未知"
            lines = [f"🔍 {name} | 状态：{stage}"]

            # 基本信息摘要
            if info.get("target_country"):
                lines.append(f"🎯 目标：{info['target_country']} / {info.get('target_major', '-')}")
            if info.get("main_instrument"):
                lines.append(f"🎵 器乐：{info['main_instrument']}")
            if info.get("responsible_person"):
                lines.append(f"👤 负责：{info['responsible_person']}")
        else:
            name = info.get("real_name", "未知")
            stage = info.get("stage", "未知")
            lines = [f"🔍 {name} | 状态：{stage}"]
            if info.get("major"):
                lines.append(f"🎵 专业：{info['major']}")

        # 跟进日志
        logs = r.get("logs", [])
        if logs:
            lines.append("")
            lines.append("📋 最近跟进：")
            for log in logs:
                log_date = ""
                if log.get("log_date"):
                    try:
                        from datetime import datetime
                        ld = log["log_date"]
                        if hasattr(ld, "strftime"):
                            log_date = ld.strftime("%m-%d")
                        else:
                            log_date = str(ld)[:5]
                    except Exception:
                        log_date = str(log["log_date"])[:10]
                elif log.get("created_at"):
                    try:
                        ca = log["created_at"]
                        log_date = ca.strftime("%m-%d") if hasattr(ca, "strftime") else str(ca)[:5]
                    except Exception:
                        log_date = ""

                note = log.get("note") or log.get("communication_topic") or log.get("academic_status") or ""
                if note:
                    lines.append(f"  {log_date} — {note}")
        else:
            lines.append("")
            lines.append("📋 暂无跟进记录")

        # 作品集
        portfolios = r.get("portfolios", [])
        lines.append("")
        lines.append(f"📂 作品集：{len(portfolios)}份")
        for idx, p in enumerate(portfolios[:5], 1):
            title = p.get("title", "未命名")
            created = ""
            if p.get("created_at"):
                try:
                    ca = p["created_at"]
                    created = ca.strftime("%m-%d") if hasattr(ca, "strftime") else str(ca)[:5]
                except Exception:
                    pass
            status = p.get("review_status", "")
            status_str = f" [{status}]" if status else ""
            lines.append(f"  {chr(0x2460 + idx - 1)} {title} ({created}){status_str}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def format_rank(ranked: list[dict]) -> str:
    """格式化销售排行"""
    today = date.today()
    lines = [f"🏆 本月销售排行（截至 {fmt_date_short(today)}）", ""]

    medals = ["🥇", "🥈", "🥉"]
    for idx, r in enumerate(ranked):
        medal = medals[idx] if idx < 3 else f"{idx + 1}."
        lines.append(f"{medal} {r['name']}  — 签约 {r['contracts']} 笔 | {fmt_amount(r['amount'])}")

    if not ranked:
        lines.append("暂无签约数据")

    return "\n".join(lines)


def format_portfolios(results: list[dict]) -> str:
    """格式化作品集查询"""
    if not results:
        return "❌ 未找到该学生"

    parts = []
    for r in results:
        portfolios = r.get("portfolios", [])
        lines = [f"📂 {r['name']} 的作品集（{len(portfolios)}份）"]
        for idx, p in enumerate(portfolios, 1):
            title = p.get("title", "未命名")
            wtype = p.get("work_type", "")
            status = p.get("review_status", "")
            deadline = ""
            if p.get("deadline"):
                try:
                    deadline = p["deadline"].strftime("%m-%d") if hasattr(p["deadline"], "strftime") else str(p["deadline"])[:10]
                except Exception:
                    pass
            meta = []
            if wtype:
                meta.append(wtype)
            if status:
                meta.append(status)
            if deadline:
                meta.append(f"截止 {deadline}")
            meta_str = f" ({' / '.join(meta)})" if meta else ""
            lines.append(f"  {idx}. {title}{meta_str}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def format_today_updates(data: dict) -> str:
    """格式化今日动态（跟进日志 + 作品集）"""
    logs = data.get("logs", [])
    portfolios = data.get("portfolios", [])

    if not logs and not portfolios:
        return ""

    today = date.today().isoformat()
    lines = [f"📋 今日动态 ({today})", ""]

    if logs:
        lines.append(f"📝 跟进日志（{len(logs)}条）")
        # 按负责人分组
        by_person = {}
        for log in logs:
            person = log.get("responsible_person") or "未分配"
            by_person.setdefault(person, []).append(log)
        for person, person_logs in by_person.items():
            lines.append(f"  [{person}]")
            for log in person_logs:
                student = log.get("student", "?")
                log_type = log.get("log_type", "")
                note = log.get("note", "")
                type_tag = f"[{log_type}] " if log_type else ""
                # 截断过长内容
                if len(note) > 80:
                    note = note[:80] + "..."
                lines.append(f"    {student} — {type_tag}{note}")
        lines.append("")

    if portfolios:
        lines.append(f"📂 新增作品集（{len(portfolios)}份）")
        for pf in portfolios:
            student = pf.get("student", "?")
            title = pf.get("title", "未命名")
            wtype = pf.get("work_type", "")
            status = pf.get("review_status", "")
            meta = [x for x in [wtype, status] if x]
            meta_str = f" ({' / '.join(meta)})" if meta else ""
            lines.append(f"  {student} — {title}{meta_str}")

    return "\n".join(lines)


def format_trend(days: list[dict]) -> str:
    """格式化趋势"""
    lines = ["📈 近7天趋势", ""]
    lines.append("日期       推荐  签约  金额")
    for d in days:
        dt = fmt_date_short(d["date"])
        lines.append(f"{dt}      {d['referrals']}     {d['contracts']}    {fmt_amount(d['amount'])}")

    return "\n".join(lines)
