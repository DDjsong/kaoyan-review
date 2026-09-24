import os
import sys
import json
from datetime import datetime, timedelta
from collections import Counter

import streamlit as st
from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import (
    StudyEvent, Question, KnowledgePoint, QuestionKP, ReviewItem, AIAdvice
)
from core import ai as ai_module

st.set_page_config(page_title="AI 老师", page_icon="🤖", layout="wide")
st.title("🤖 AI 老师")
st.caption("基于你所有做题记录的整体诊断，越用越懂你")

session = get_session()


# ---------- 1. 收集数据 ----------
events = session.query(StudyEvent).filter(StudyEvent.item_type == "question").all()
total = len(events)
correct = sum(1 for e in events if e.is_correct)
accuracy = correct / total * 100 if total else 0

# 顶部状态卡
c1, c2, c3, c4 = st.columns(4)
c1.metric("累计做题", total)
c2.metric("正确率", f"{accuracy:.1f}%")
c3.metric("错题数", total - correct)
due_now = session.query(ReviewItem).filter(
    ReviewItem.item_type == "question",
    ReviewItem.due <= datetime.now(),
    ReviewItem.state != "archived",
).count()
c4.metric("待复习", due_now)

st.markdown("---")

if total == 0:
    st.info("还没有做题记录，先去刷题吧。")
    st.stop()


# ---------- 2. 构建摘要 ----------
def build_summary():
    lines = []

    # 整体
    lines.append(f"累计做题 {total} 道，正确 {correct} 道，正确率 {accuracy:.1f}%。")

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
    for ch, acc, t in chap_rows:
        lines.append(f"  - {ch}: {acc:.0f}%（{t} 道）")

    # 错因分布
    err_counter = Counter(e.error_type for e in events if e.is_correct is False and e.error_type)
    if err_counter:
        lines.append("\n错因分布：")
        for k, v in err_counter.most_common():
            lines.append(f"  - {k}: {v} 次")

    # 薄弱知识点
    wrong_qids = [e.item_id for e in events if e.is_correct is False]
    if wrong_qids:
        kp_rows = (session.query(KnowledgePoint.name)
                   .join(QuestionKP, QuestionKP.kp_id == KnowledgePoint.id)
                   .filter(QuestionKP.question_id.in_(wrong_qids))
                   .all())
        kp_counter = Counter(name for (name,) in kp_rows)
        top_kps = kp_counter.most_common(10)
        if top_kps:
            lines.append("\n薄弱知识点 TOP 10（按错误次数）：")
            for name, cnt in top_kps:
                lines.append(f"  - {name}: {cnt} 次")

    # 最近 10 道错题
    recent_wrong_events = (
        session.query(StudyEvent)
        .filter(StudyEvent.item_type == "question", StudyEvent.is_correct == False)
        .order_by(StudyEvent.created_at.desc())
        .limit(10).all()
    )
    if recent_wrong_events:
        lines.append("\n最近 10 道错题（题干前 50 字 + 错因）：")
        for e in recent_wrong_events:
            q = session.query(Question).filter(Question.id == e.item_id).first()
            if q:
                lines.append(f"  - [{q.year}年] {q.stem[:50]} | 错因：{e.error_type or '未选'}")

    return "\n".join(lines)


# ---------- 3. 读取上次建议 ----------
last = (session.query(AIAdvice).order_by(AIAdvice.created_at.desc()).first())
last_advice_text = ""
if last and last.advice_json:
    try:
        last_data = json.loads(last.advice_json)
        last_advice_text = json.dumps(last_data, ensure_ascii=False, indent=2)
    except Exception:
        last_advice_text = ""

# ---------- 4. 触发分析 ----------
if st.button("🧠 让 AI 老师分析我现在的状态", type="primary"):
    with st.spinner("AI 老师正在分析你的学习数据..."):
        summary_text = build_summary()
        result = ai_module.analyze_overall(summary_text, last_advice_text)
        if "overall" in result and "解析失败" not in str(result.get("overall", "")):
            adv = AIAdvice(
                advice_json=json.dumps(result, ensure_ascii=False),
                stats_snapshot=summary_text,
            )
            session.add(adv)
            session.commit()
        st.session_state["ai_overall"] = result
        st.rerun()

# ---------- 5. 显示结果 ----------
if "ai_overall" in st.session_state:
    r = st.session_state["ai_overall"]
    with st.container(border=True):
        st.markdown("### 🎯 整体状态")
        st.markdown(r.get("overall", "—"))

        if r.get("weak_chapters"):
            st.markdown("### ⚠️ 薄弱章节")
            for ch in r["weak_chapters"]:
                st.markdown(f"- {ch}")

        if r.get("weak_kps"):
            st.markdown("### ⚠️ 薄弱知识点")
            for kp in r["weak_kps"]:
                st.markdown(f"- {kp}")

        if r.get("suggestions"):
            st.markdown("### 💡 学习建议")
            for i, s in enumerate(r["suggestions"], 1):
                st.markdown(f"{i}. {s}")

        if r.get("next_focus"):
            st.success(f"📌 **下一步重点**：{r['next_focus']}")

    st.markdown("---")

# ---------- 6. 历史建议 ----------
st.markdown("### 📜 历史建议")
history = (session.query(AIAdvice).order_by(AIAdvice.created_at.desc()).limit(10).all())
if not history:
    st.caption("还没有历史建议")
else:
    for h in history:
        try:
            data = json.loads(h.advice_json)
        except Exception:
            continue
        ts = h.created_at.strftime("%Y-%m-%d %H:%M")
        with st.expander(f"🕐 {ts} · {data.get('overall', '')[:40]}..."):
            st.markdown(f"**整体状态**：{data.get('overall', '—')}")
            if data.get("weak_chapters"):
                st.markdown(f"**薄弱章节**：{', '.join(data['weak_chapters'])}")
            if data.get("weak_kps"):
                st.markdown(f"**薄弱知识点**：{', '.join(data['weak_kps'])}")
            if data.get("suggestions"):
                st.markdown("**建议**：")
                for s in data["suggestions"]:
                    st.markdown(f"- {s}")
            if data.get("next_focus"):
                st.markdown(f"**下一步**：{data['next_focus']}")