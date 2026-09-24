import os
import sys
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import StudyEvent, Question, KnowledgePoint, QuestionKP, ReviewItem

st.set_page_config(page_title="总结", page_icon="📊", layout="wide")
st.title("📊 学习总结")

session = get_session()

# ---------------- 时间范围 ----------------
range_option = st.radio(
    "时间范围",
    ["今日", "近 7 天", "近 30 天", "全部"],
    horizontal=True,
    index=1,
)

now = datetime.now()
if range_option == "今日":
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
elif range_option == "近 7 天":
    start = now - timedelta(days=7)
elif range_option == "近 30 天":
    start = now - timedelta(days=30)
else:
    start = None

# ---------------- 拉取事件 ----------------
q = session.query(StudyEvent).filter(StudyEvent.item_type == "question")
if start:
    q = q.filter(StudyEvent.created_at >= start)
events = q.all()

if not events:
    st.info("所选时间范围内还没有学习记录。去刷题吧！")
    st.stop()

# 总览
total = len(events)
correct_count = sum(1 for e in events if e.is_correct)
wrong_count = total - correct_count
accuracy = correct_count / total * 100 if total else 0

# ---------------- 顶部统计卡片 ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("做题总数", total)
c2.metric("正确", correct_count)
c3.metric("错误", wrong_count)
c4.metric("正确率", f"{accuracy:.1f}%")

st.markdown("---")

# 通用 Altair 样式
AXIS_STYLE = dict(
    labelFontSize=13,
    titleFontSize=13,
    tickSize=0,
    domainColor="#666",
    domainWidth=1,
    gridColor="#333",
    gridOpacity=0.3,
    labelColor="#ddd",
    titleColor="#ddd",
)

BLUE = "#5B9BD5"


# ---------------- 回忆自评分布 ----------------
st.markdown("### 🧠 回忆自评分布")
self_counts = {
    "remember": sum(1 for e in events if e.self_rating == "remember"),
    "fuzzy": sum(1 for e in events if e.self_rating == "fuzzy"),
    "forgot": sum(1 for e in events if e.self_rating == "forgot"),
}
self_df = pd.DataFrame({
    "自评": ["记得", "模糊", "忘记"],
    "次数": [self_counts["remember"], self_counts["fuzzy"], self_counts["forgot"]],
})

base = alt.Chart(self_df).encode(
    x=alt.X(
        "自评:N",
        axis=alt.Axis(labelAngle=0, title=None, **AXIS_STYLE),
        sort=["记得", "模糊", "忘记"],
    ),
    y=alt.Y(
        "次数:Q",
        axis=alt.Axis(title=None, **AXIS_STYLE),
    ),
)
bars = base.mark_bar(size=80, cornerRadius=6, color=BLUE)
labels = base.mark_text(dy=-10, fontSize=14, color="#ddd").encode(text="次数:Q")
st.altair_chart((bars + labels).properties(height=300), use_container_width=True)

# ---------------- 错因分布 ----------------
st.markdown("### 🩺 错因分布")
err_counts = {}
for e in events:
    if e.is_correct is False and e.error_type:
        err_counts[e.error_type] = err_counts.get(e.error_type, 0) + 1

if err_counts:
    err_df = pd.DataFrame({
        "错因": list(err_counts.keys()),
        "次数": list(err_counts.values()),
    }).sort_values("次数", ascending=False)

    base = alt.Chart(err_df).encode(
        x=alt.X(
            "错因:N",
            axis=alt.Axis(labelAngle=0, title=None, **AXIS_STYLE),
            sort=err_df["错因"].tolist(),
        ),
        y=alt.Y(
            "次数:Q",
            axis=alt.Axis(title=None, **AXIS_STYLE),
        ),
    )
    bars = base.mark_bar(size=80, cornerRadius=6, color="#E06C75")
    labels = base.mark_text(dy=-10, fontSize=14, color="#ddd").encode(text="次数:Q")
    st.altair_chart((bars + labels).properties(height=300), use_container_width=True)
else:
    st.caption("暂无错误记录")

st.markdown("---")

# ---------------- 薄弱知识点 TOP 10 ----------------
st.markdown("### 📌 薄弱知识点 TOP 10")
st.caption("根据错题关联的知识点统计")

wrong_qids = [e.item_id for e in events if e.is_correct is False]

if wrong_qids:
    kp_counter = {}
    rows = (
        session.query(QuestionKP.kp_id, KnowledgePoint.name)
        .join(KnowledgePoint, KnowledgePoint.id == QuestionKP.kp_id)
        .filter(QuestionKP.question_id.in_(wrong_qids))
        .all()
    )
    for kp_id, kp_name in rows:
        kp_counter[kp_name] = kp_counter.get(kp_name, 0) + 1

    top_kps = sorted(kp_counter.items(), key=lambda x: -x[1])[:10]
    if top_kps:
        kp_df = pd.DataFrame(top_kps, columns=["知识点", "错误次数"])
        kp_df.index = range(1, len(kp_df) + 1)
        st.dataframe(kp_df, use_container_width=True)
    else:
        st.caption("错题没有关联知识点")
else:
    st.success("🎉 所选时间范围内没有错题")

st.markdown("---")

# ---------------- 章节掌握度 ----------------
st.markdown("### 📚 章节掌握度")
st.caption("按题目的章节统计做题情况")

qid_to_chapter = dict(
    session.query(Question.id, Question.chapter_name)
    .filter(Question.id.in_([e.item_id for e in events]))
    .all()
)

chapter_stats = {}
for e in events:
    ch = qid_to_chapter.get(e.item_id) or "未分类"
    if ch not in chapter_stats:
        chapter_stats[ch] = {"total": 0, "correct": 0}
    chapter_stats[ch]["total"] += 1
    if e.is_correct:
        chapter_stats[ch]["correct"] += 1

if chapter_stats:
    chapter_rows = []
    for ch, s in chapter_stats.items():
        acc = s["correct"] / s["total"] * 100 if s["total"] else 0
        chapter_rows.append({
            "章节": ch,
            "做题数": s["total"],
            "正确数": s["correct"],
            "正确率": round(acc, 1),
        })
    chapter_df = pd.DataFrame(chapter_rows).sort_values("正确率")

    # 横向条形图（章节名长，横着看好读）
    bars = alt.Chart(chapter_df).mark_bar(size=24, cornerRadius=6, color=BLUE).encode(
        y=alt.Y(
            "章节:N",
            axis=alt.Axis(title=None, **AXIS_STYLE),
            sort=chapter_df["章节"].tolist(),
        ),
        x=alt.X(
            "正确率:Q",
            axis=alt.Axis(title="正确率 (%)", **AXIS_STYLE),
            scale=alt.Scale(domain=[0, 100]),
        ),
        tooltip=["章节", "做题数", "正确数", "正确率"],
    )
    labels = alt.Chart(chapter_df).mark_text(
        align="left", dx=6, fontSize=13, color="#ddd"
    ).encode(
        y=alt.Y("章节:N", sort=chapter_df["章节"].tolist()),
        x=alt.X("正确率:Q"),
        text=alt.Text("正确率:Q", format=".1f"),
    )
    st.altair_chart((bars + labels).properties(height=max(300, len(chapter_df) * 40)),
                    use_container_width=True)

    st.markdown("##### 📋 详细数据")
    st.dataframe(chapter_df, use_container_width=True, hide_index=True)
else:
    st.caption("暂无章节数据")

st.markdown("---")

# ---------------- 复习进度 ----------------
st.markdown("### ⏱ 复习进度")
total_reviews = session.query(ReviewItem).filter(ReviewItem.item_type == "question").count()
due_now = session.query(ReviewItem).filter(
    ReviewItem.item_type == "question",
    ReviewItem.due <= now,
    ReviewItem.state != "archived",
).count()
archived = session.query(ReviewItem).filter(
    ReviewItem.item_type == "question",
    ReviewItem.state == "archived",
).count()

c1, c2, c3 = st.columns(3)
c1.metric("总题数", total_reviews)
c2.metric("待复习", due_now)
c3.metric("已归档", archived)