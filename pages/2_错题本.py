import os
import sys
from datetime import datetime

import streamlit as st
import pandas as pd
from sqlalchemy import desc

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, StudyEvent, ReviewItem, KnowledgePoint, QuestionKP

st.set_page_config(page_title="错题本", page_icon="📕", layout="wide")
st.title("📕 错题本")

session = get_session()

# 找出所有有错误记录的题目 id
error_qids = [
    row[0] for row in
    session.query(StudyEvent.item_id)
    .filter(StudyEvent.item_type == "question", StudyEvent.is_correct == False)
    .distinct()
    .all()
]

if not error_qids:
    st.info("🎉 还没有错题。先去刷题吧！")
    st.stop()

# 取出这些题目 + 对应的复习项
rows = (
    session.query(Question, ReviewItem)
    .join(ReviewItem, (ReviewItem.item_type == "question") & (ReviewItem.item_id == Question.id))
    .filter(Question.id.in_(error_qids))
    .order_by(ReviewItem.due)
    .all()
)

active = [r for r in rows if r[1].state != "archived"]
archived = [r for r in rows if r[1].state == "archived"]

# 顶部统计
c1, c2, c3 = st.columns(3)
c1.metric("待复习错题", len(active))
c2.metric("已归档错题", len(archived))
c3.metric("总错题数", len(rows))

st.markdown("---")

tab1, tab2 = st.tabs(["🔥 待复习", "📦 已归档"])

# ---------------- 待复习 ----------------
with tab1:
    if not active:
        st.info("🎉 暂无待复习错题")
    else:
        # 薄弱知识点 TOP 10
        st.markdown("### 🩺 薄弱知识点 TOP 10")
        kp_errors = {}
        for q, ri in active:
            kps = (
                session.query(KnowledgePoint)
                .join(QuestionKP, QuestionKP.kp_id == KnowledgePoint.id)
                .filter(QuestionKP.question_id == q.id)
                .all()
            )
            for kp in kps:
                kp_errors.setdefault(kp.name, []).append(q.id)

        sorted_kps = sorted(kp_errors.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        if sorted_kps:
            df = pd.DataFrame({
                "知识点": [k[0] for k in sorted_kps],
                "错误题数": [len(k[1]) for k in sorted_kps],
            })
            st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 📝 错题列表")

        for q, ri in active:
            with st.expander(f"❓ [{q.year}年] {q.stem[:50]}..."):
                st.markdown(f"**题干**: {q.stem}")
                st.markdown(f"**答案**: {q.answer}")
                st.markdown(f"**知识点**: {q.kp_text or '—'}")

                last_evt = (
                    session.query(StudyEvent)
                    .filter(
                        StudyEvent.item_type == "question",
                        StudyEvent.item_id == q.id,
                        StudyEvent.is_correct == False,
                    )
                    .order_by(desc(StudyEvent.created_at))
                    .first()
                )
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("最近错因", last_evt.error_type if last_evt else "—")
                col2.metric("复习次数", ri.reps)
                col3.metric("下次复习", ri.due.strftime("%m-%d") if ri.due else "—")
                col4.metric("当前间隔", f"{ri.interval} 天")

                if st.button(f"📦 手动归档", key=f"arch_{q.id}"):
                    ri.state = "archived"
                    session.commit()
                    st.rerun()

# ---------------- 已归档 ----------------
with tab2:
    if not archived:
        st.info("暂无归档错题")
    else:
        for q, ri in archived:
            with st.expander(f"✅ [{q.year}年] {q.stem[:50]}..."):
                st.markdown(f"**题干**: {q.stem}")
                st.markdown(f"**答案**: {q.answer}")
                if st.button(f"🔄 恢复复习", key=f"restore_{q.id}"):
                    ri.state = "learning"
                    ri.reps = 0
                    ri.interval = 1
                    ri.due = datetime.now()
                    session.commit()
                    st.rerun()