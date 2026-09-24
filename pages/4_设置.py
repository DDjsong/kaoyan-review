import os
import sys
from datetime import datetime
from io import BytesIO

import streamlit as st
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session, DB_PATH
from core.models import (
    Question, KnowledgePoint, QuestionKP, ReviewItem, StudyEvent, AIAdvice
)
from core.settings import (
    load_settings, save_settings, get_chapter_importance
)

st.set_page_config(page_title="设置", page_icon="⚙️", layout="wide")
st.title("⚙️ 设置")

session = get_session()
settings = load_settings()

tab1, tab2, tab3, tab4 = st.tabs([
    "🎯 学习目标", "⭐ 重点权重", "🤖 AI 功能", "💾 数据管理",
])


# ========================================================
# Tab 1：学习目标（每轮题数）
# ========================================================
with tab1:
    st.markdown("### 每轮题数")
    st.caption("在刷题页点「开始本轮」时，默认使用这个数字")

    new_size = st.number_input(
        "每轮题数", min_value=1, max_value=200,
        value=int(settings.get("round_size", 20)), step=5,
    )
    new_exam = st.text_input(
        "考试日期（可选，格式 YYYY-MM-DD）",
        value=settings.get("exam_date", ""),
        placeholder="例如 2025-12-20",
    )

    if st.button("💾 保存学习目标", type="primary"):
        settings["round_size"] = new_size
        settings["exam_date"] = new_exam.strip()
        save_settings(settings)
        st.success("已保存")

    st.markdown("---")
    st.markdown("#### 当前设置")
    c1, c2 = st.columns(2)
    c1.metric("每轮题数", f"{settings.get('round_size', 20)} 题")
    if settings.get("exam_date"):
        try:
            exam = datetime.strptime(settings["exam_date"], "%Y-%m-%d")
            days = (exam - datetime.now()).days
            c2.metric("距离考试", f"{days} 天")
        except Exception:
            c2.metric("考试日期", settings["exam_date"])
    else:
        c2.metric("考试日期", "未设置")


# ========================================================
# Tab 2：重点权重（章节 + 知识点两层）
# ========================================================
with tab2:
    st.markdown("### 📚 章节权重")
    st.caption("1-5 分：影响该章节题目被抽到的概率。默认 3")

    chapters_all = [
        r[0] for r in session.query(Question.chapter_name).distinct().all()
        if r[0]
    ]
    chapters_all.sort()

    for chap in chapters_all:
        cur = get_chapter_importance(chap)
        new_val = st.slider(
            chap,
            min_value=1, max_value=5,
            value=int(cur),
            key=f"chap_slider_{chap}",
        )
        if new_val != cur:
            chapter_imp = settings.get("chapter_importance", {})
            chapter_imp[chap] = new_val
            settings["chapter_importance"] = chapter_imp
            save_settings(settings)

    st.markdown("---")
    st.markdown("### ⭐ 知识点权重（细化）")
    st.caption("展开章节，逐个调整知识点。影响该章节内题目被抽到的相对概率")

    for chap in chapters_all:
        # 该章的知识点（去重）
        kp_rows = (
            session.query(KnowledgePoint)
            .join(QuestionKP, QuestionKP.kp_id == KnowledgePoint.id)
            .join(Question, Question.id == QuestionKP.question_id)
            .filter(Question.chapter_name == chap)
            .distinct()
            .order_by(KnowledgePoint.name)
            .all()
        )
        if not kp_rows:
            continue

        with st.expander(f"📚 {chap}（{len(kp_rows)} 个知识点）", expanded=False):
            changed = False
            for kp in kp_rows:
                new_val = st.slider(
                    kp.name,
                    min_value=1, max_value=5,
                    value=int(kp.importance),
                    key=f"kp_slider_{kp.id}",
                )
                if new_val != kp.importance:
                    kp.importance = new_val
                    session.add(kp)
                    changed = True
            if changed:
                session.commit()

    st.markdown("---")
    st.caption("💡 提示：拖动滑块后立即保存，无需点确认按钮")


# ========================================================
# Tab 3：AI 功能
# ========================================================
with tab3:
    st.markdown("### AI 功能开关")
    st.caption("关闭后，刷题页将不显示对应的 AI 按钮，节省 API 调用")

    ai_diag = st.toggle(
        "刷题页 AI 错因诊断",
        value=settings.get("ai_diagnose_enabled", True),
    )
    ai_overall = st.toggle(
        "AI 老师整体分析",
        value=settings.get("ai_overall_enabled", True),
    )
    chapter_fallback = st.toggle(
        "『再做一道』找不到相似知识点时，按章节抽题",
        value=settings.get("similar_by_chapter_fallback", False),
        help="题库较小时建议打开，能找到同章节的其他题",
    )

    if st.button("💾 保存 AI 设置", type="primary"):
        settings["ai_diagnose_enabled"] = ai_diag
        settings["ai_overall_enabled"] = ai_overall
        settings["similar_by_chapter_fallback"] = chapter_fallback
        save_settings(settings)
        st.success("已保存")

    st.markdown("---")
    st.markdown("#### API 状态")
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    if has_key:
        st.success("✅ 已检测到 DEEPSEEK_API_KEY 环境变量")
    else:
        st.error("❌ 未检测到 DEEPSEEK_API_KEY，请检查系统环境变量")


# ========================================================
# Tab 4：数据管理
# ========================================================
with tab4:
    st.markdown("### 数据统计")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("题目", session.query(Question).count())
    c2.metric("知识点", session.query(KnowledgePoint).count())
    c3.metric("学习记录", session.query(StudyEvent).count())
    c4.metric("AI 建议", session.query(AIAdvice).count())

    st.markdown("---")
    st.markdown("### 导出数据")

    # 导出题目
    if st.button("📤 导出题目为 CSV"):
        rows = session.query(Question).all()
        df = pd.DataFrame([{
            "id": q.id, "章节": q.chapter_name, "年份": q.year,
            "题干": q.stem, "答案": q.answer, "知识点": q.kp_text,
        } for q in rows])
        buf = BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ 点击下载 questions.csv",
            data=buf.getvalue(),
            file_name=f"questions_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
        )

    # 导出学习记录
    if st.button("📤 导出学习记录为 CSV"):
        events = session.query(StudyEvent).filter(
            StudyEvent.item_type == "question"
        ).order_by(StudyEvent.created_at).all()
        qid_to_stem = {q.id: (q.stem[:60], q.chapter_name, q.year)
                       for q in session.query(Question).all()}
        rows = []
        for e in events:
            stem, chap, year = qid_to_stem.get(e.item_id, ("", "", ""))
            rows.append({
                "时间": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else "",
                "题号": e.item_id,
                "年份": year,
                "章节": chap,
                "题干前60字": stem,
                "自评": e.self_rating or "",
                "是否正确": "✅" if e.is_correct else "❌",
                "错因": e.error_type or "",
            })
        df = pd.DataFrame(rows)
        buf = BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        st.download_button(
            "⬇️ 点击下载 study_events.csv",
            data=buf.getvalue(),
            file_name=f"study_events_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
        )

    st.markdown("---")
    st.markdown("### 数据库备份")

    st.caption(f"数据库位置：`{DB_PATH}`")

    if st.button("💾 生成备份文件"):
        if os.path.exists(DB_PATH):
            buf = BytesIO()
            with open(DB_PATH, "rb") as f:
                buf.write(f.read())
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "⬇️ 点击下载数据库备份",
                data=buf.getvalue(),
                file_name=f"kaoyan_backup_{ts}.db",
                mime="application/octet-stream",
            )
        else:
            st.error("数据库文件不存在")

    st.markdown("---")
    st.markdown("### ⚠️ 危险操作")

    with st.expander("清空所有学习记录（保留题库）"):
        st.warning("这会删除所有做题历史、错题记录、AI 建议，但保留题目和知识点。")
        confirm = st.text_input("输入 `DELETE` 确认", key="wipe_confirm")
        if st.button("🔴 执行清空", key="wipe_btn"):
            if confirm == "DELETE":
                session.query(StudyEvent).delete()
                session.query(AIAdvice).delete()
                session.query(ReviewItem).delete()
                session.commit()
                # 重新创建所有复习项
                for (qid,) in session.query(Question.id).all():
                    session.add(ReviewItem(item_type="question", item_id=qid))
                session.commit()
                st.success("已清空学习记录")
                st.rerun()
            else:
                st.error("请输入 DELETE")