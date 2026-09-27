import os
import json
import re
from openai import OpenAI

_client = None


def _get_api_key():
    """优先从 Streamlit Secrets 读，其次从环境变量读"""
    # 1) Streamlit Secrets（部署在 Cloud 时）
    try:
        import streamlit as st
        if "DEEPSEEK_API_KEY" in st.secrets:
            return st.secrets["DEEPSEEK_API_KEY"]
    except Exception:
        pass
    # 2) 系统环境变量（本地开发时）
    return os.environ.get("DEEPSEEK_API_KEY")


def get_client():
    global _client
    if _client is None:
        api_key = _get_api_key()
        if not api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY。本地请设置系统环境变量；"
                "云端请在 Streamlit Cloud 的 Secrets 里配置。"
            )
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _client

def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _call(prompt, system="你是生物化学考研辅导老师，只返回 JSON。"):
    client = get_client()
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=800,
    )
    return resp.choices[0].message.content


# ==================== AI 错因诊断（三道） ====================

DIAG_SUMMARY = """学生做错了一道生物化学考研真题。

【题目】{stem}
【答案】{answer}
【知识点】{kp_text}
【回忆自评】{self_rating}
【错因】{error_type}

只返回 JSON，不要多余文字：
{{
  "error_analysis": "100字内分析为什么错",
  "weak_points": ["薄弱知识点1", "薄弱知识点2", "薄弱知识点3"]
}}"""

DIAG_TEACHING = """学生错题：
【题目】{stem}
【答案】{answer}
【知识点】{kp_text}

只返回 JSON：
{{
  "explanation": "300字内以老师口吻讲透这道题涉及的原理",
  "memory_tips": "100字内记忆技巧（口诀/对比/联想）"
}}"""

DIAG_LINK = """学生错题：
【题目】{stem}
【知识点】{kp_text}

只返回 JSON：
{{
  "confused_with": ["容易混淆的概念1", "概念2"],
  "similar_kps": ["相近知识点1", "相近知识点2", "相近知识点3"]
}}"""


def diagnose_summary(stem, answer, kp_text, self_rating, error_type):
    prompt = DIAG_SUMMARY.format(
        stem=stem, answer=answer or "（无）", kp_text=kp_text or "（无）",
        self_rating=self_rating or "未记录", error_type=error_type or "未选择",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"error_analysis": f"（解析失败：{e}）"}


def diagnose_teaching(stem, answer, kp_text):
    prompt = DIAG_TEACHING.format(
        stem=stem, answer=answer or "（无）", kp_text=kp_text or "（无）",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"explanation": f"（解析失败：{e}）", "memory_tips": ""}


def diagnose_link(stem, kp_text):
    prompt = DIAG_LINK.format(stem=stem, kp_text=kp_text or "（无）")
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"confused_with": [], "similar_kps": []}


# ==================== AI 老师（全局） ====================

OVERALL_PROMPT = """你是一位考研辅导老师，正在给一位学生做整体学习状态诊断。

【学生当前数据】
{summary}

【你上次给这位学生的建议（如果有）】
{last_advice}

请综合分析，只返回 JSON：
{{
  "overall": "整体状态概述，80字内",
  "weak_chapters": ["薄弱章节1", "薄弱章节2"],
  "weak_kps": ["薄弱知识点1", "2", "3"],
  "suggestions": ["建议1（30字内）", "建议2", "建议3"],
  "next_focus": "接下来一周重点复习方向，50字内"
}}"""


def analyze_overall(summary_text, last_advice_text=""):
    prompt = OVERALL_PROMPT.format(
        summary=summary_text,
        last_advice=last_advice_text or "（无，第一次分析）",
    )
    try:
        return _extract_json(_call(prompt))
    except Exception as e:
        return {"overall": f"（解析失败：{e}）"}

CHAT_SYSTEM_TEMPLATE = """你是一位资深生物化学考研辅导老师，正在一对一辅导一位学生。

以下是这位学生的真实学习数据：

{student_context}

【回复要求】
- 中文回答，语气亲切专业
- 结合学生的真实学习数据，不要说空话
- 学生问知识点时，讲清楚原理、易错点、记忆方法
- 学生问学习建议时，基于数据给出具体可执行的建议
- 回答简洁，控制在 400 字以内
- 不编造数据，不引用不存在的错题或笔记
"""


def _build_student_context(session):
    """构建学生数据摘要，作为 AI 的上下文"""
    from core.models import StudyEvent, Question, KnowledgePoint, QuestionKP
    from collections import Counter

    events = session.query(StudyEvent).filter(
        StudyEvent.item_type == "question"
    ).all()
    if not events:
        return "学生还没有做题记录。"

    total = len(events)
    correct = sum(1 for e in events if e.is_correct)
    accuracy = correct / total * 100 if total else 0

    lines = [f"累计做题 {total} 道，正确 {correct} 道，正确率 {accuracy:.1f}%。"]

    # 章节正确率
    qid_to_chap = dict(session.query(Question.id, Question.chapter_name).all())
    chap_stat = {}
    for e in events:
        ch = qid_to_chap.get(e.item_id) or "未分类"
        chap_stat.setdefault(ch, {"t": 0, "c": 0})
        chap_stat[ch]["t"] += 1
        if e.is_correct:
            chap_stat[ch]["c"] += 1
    chap_rows = sorted(
        [(ch, s["c"] / s["t"] * 100, s["t"]) for ch, s in chap_stat.items()],
        key=lambda x: x[1],
    )
    lines.append("\n各章节正确率（从低到高）：")
    for ch, acc, t in chap_rows[:8]:
        lines.append(f"  - {ch}: {acc:.0f}%（{t} 道）")

    # 错因分布
    err_counter = Counter(e.error_type for e in events if e.is_correct is False and e.error_type)
    if err_counter:
        lines.append("\n错因分布：")
        for k, v in err_counter.most_common():
            lines.append(f"  - {k}: {v} 次")

    # 薄弱知识点 TOP 8
    wrong_qids = [e.item_id for e in events if e.is_correct is False]
    if wrong_qids:
        kp_rows = (session.query(KnowledgePoint.name)
                   .join(QuestionKP, QuestionKP.kp_id == KnowledgePoint.id)
                   .filter(QuestionKP.question_id.in_(wrong_qids)).all())
        kp_counter = Counter(name for (name,) in kp_rows)
        top_kps = kp_counter.most_common(8)
        if top_kps:
            lines.append("\n薄弱知识点 TOP 8：")
            for name, cnt in top_kps:
                lines.append(f"  - {name}: {cnt} 次")

    # 最近 15 道错题（含错因、笔记）
    recent_wrong = (session.query(StudyEvent)
                    .filter(StudyEvent.item_type == "question",
                            StudyEvent.is_correct == False)
                    .order_by(StudyEvent.created_at.desc())
                    .limit(15).all())
    if recent_wrong:
        lines.append("\n最近 15 道错题：")
        for e in recent_wrong:
            q = session.query(Question).filter(Question.id == e.item_id).first()
            if not q:
                continue
            line = f"  - [{q.year}年] {q.stem[:50]} | 错因：{e.error_type or '未选'}"
            if e.note:
                line += f" | 笔记：{e.note[:80]}"
            lines.append(line)

    # 学生自评统计
    self_counter = Counter(e.self_rating for e in events if e.self_rating)
    if self_counter:
        lines.append("\n回忆自评分布：")
        for k, v in self_counter.most_common():
            lines.append(f"  - {k}: {v} 次")

    return "\n".join(lines)


def chat_with_ai(session, user_message, history):
    """与 AI 对话。
    session: 数据库 session
    user_message: 用户本轮消息
    history: [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    student_context = _build_student_context(session)
    system_prompt = CHAT_SYSTEM_TEMPLATE.format(student_context=student_context)

    messages = [{"role": "system", "content": system_prompt}]
    # 只保留最近 8 轮对话，避免过长
    for h in history[-16:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})

    client = get_client()
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=0.5,
        max_tokens=1000,
    )
    return resp.choices[0].message.content