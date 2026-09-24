import os
import sys
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import altair as alt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, ReviewItem, StudyEvent, KnowledgePoint, QuestionKP
from core import ai as ai_module
from core import quiz as quiz_module
from core.settings import load_settings

st.set_page_config(page_title="刷题", page_icon="📖", layout="wide")

session = get_session()
settings = load_settings()

# ---------------- 状态 ----------------
for key, default in [
    ("round_phase", "cover"),        # cover / quiz / summary
    ("round_size", settings.get("round_size", 20)),
    ("round_index", 0),
    ("round_events", []),
    ("round_chapter", "全部章节"),
    ("qid", None),
    ("phase", "question"),           # question / answer_confirm / error_select
    ("self_rating", None),
    ("skip_ids", set()),
    ("return_to_qid", None),
    ("last_question_info", None),
    ("last_ai_summary", None),
    ("last_ai_teaching", None),
    ("last_ai_link", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ========================================================
# 阶段 1：封面
# ========================================================
if st.session_state.round_phase == "cover":
    st.title("📖 开始新一轮")

    # 从设置读（只读展示）
    round_size = int(settings.get("round_size", 20))

    chapters = [r[0] for r in session.query(Question.chapter_name).distinct().all() if r[0]]
    chapters.sort()
    chapter_options = ["错题本", "全部章节"] + chapters

    # 错题本数量预览
    wrong_qids_count = len(set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question",
                StudyEvent.is_correct == False)
        .distinct().all()
    ))

    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("### 📚 出题范围")
        # 默认选中 "全部章节"
        default_idx = 1
        if st.session_state.round_chapter in chapter_options:
            default_idx = chapter_options.index(st.session_state.round_chapter)
        chapter_choice = st.selectbox(
            "选择范围", chapter_options,
            index=default_idx,
            key="cover_chapter",
        )
        if chapter_choice == "错题本":
            if wrong_qids_count == 0:
                st.warning("错题本里暂时没有题。先去刷几道，做错了才会进错题本。")
            else:
                st.info(f"📕 错题本中共有 **{wrong_qids_count}** 道题")

    with c2:
        st.markdown("### 🔢 本轮题数")
        st.markdown(f"## {round_size} 题")
        st.caption("如需修改，请到【⚙️ 设置 → 学习目标】")

    st.markdown("---")
    st.markdown("### 🎯 抽题规则")
    if chapter_choice == "错题本":
        st.caption(
            "**错题本模式**：只从你做错过的题里抽，优先复习到期错题。\n\n"
            "连续答对 3 次且间隔超过 30 天的题会**归档**，不再出现在错题本。"
        )
    else:
        st.caption(
            "系统按以下优先级加权抽题（自动排除本轮已做、已跳过的题）：\n\n"
            "1. **50%** 到期复习题（错题、学过的题）\n"
            "2. **25%** 高权重知识点题目（重点知识点）\n"
            "3. **15%** 新题（从未做过）\n"
            "4. **10%** 其他随机\n\n"
            "在【设置 → 重点权重】里调整章节/知识点权重，会影响抽取。"
        )

    st.markdown("---")

    # 开始按钮（错题本为空时禁用）
    can_start = True
    if chapter_choice == "错题本" and wrong_qids_count == 0:
        can_start = False

    if st.button("🚀 开始本轮", type="primary",
                 use_container_width=True, disabled=not can_start):
        st.session_state.round_chapter = chapter_choice
        st.session_state.round_size = round_size
        st.session_state.round_index = 0
        st.session_state.round_events = []
        st.session_state.qid = None
        st.session_state.phase = "question"
        st.session_state.self_rating = None
        st.session_state.skip_ids = set()
        st.session_state.return_to_qid = None
        st.session_state.last_question_info = None
        st.session_state.last_ai_summary = None
        st.session_state.last_ai_teaching = None
        st.session_state.last_ai_link = None
        st.session_state.round_phase = "quiz"
        st.rerun()

    st.stop()


# ========================================================
# 阶段 2：做题
# ========================================================
if st.session_state.round_phase == "quiz":
    st.title("📖 刷题")

    total = st.session_state.round_size
    done = st.session_state.round_index
    st.progress(done / total if total else 0, text=f"进度：{done} / {total}")

    def finish_question(qid, correct, error_type):
        session.add(StudyEvent(
            item_type="question", item_id=qid,
            self_rating=st.session_state.self_rating,
            is_correct=correct, error_type=error_type,
        ))
        ri = (session.query(ReviewItem)
              .filter(ReviewItem.item_type == "question", ReviewItem.item_id == qid)
              .first())
        if ri is None:
            ri = ReviewItem(item_type="question", item_id=qid)
            session.add(ri)
            session.flush()
        if correct:
            ri.reps += 1
            ri.interval = max(1, int(ri.interval * ri.ease)) if ri.interval > 0 else 1
            ri.ease = min(2.5, ri.ease + 0.1)
            ri.state = "archived" if (ri.reps >= 3 and ri.interval > 30) else "review"
        else:
            ri.reps = 0
            ri.interval = 1
            ri.ease = max(1.3, ri.ease - 0.2)
            ri.state = "learning"
        ri.due = datetime.now() + timedelta(days=ri.interval)
        session.commit()

        q_obj = session.query(Question).filter(Question.id == qid).first()
        st.session_state.round_events.append({
            "qid": qid, "stem": q_obj.stem, "year": q_obj.year,
            "chapter": q_obj.chapter_name,
            "self_rating": st.session_state.self_rating,
            "is_correct": correct, "error_type": error_type,
        })
        st.session_state.last_question_info = {
            "qid": qid, "stem": q_obj.stem, "answer": q_obj.answer,
            "kp_text": q_obj.kp_text, "year": q_obj.year,
            "chapter": q_obj.chapter_name,
            "self_rating": st.session_state.self_rating,
            "error_type": error_type, "is_correct": correct,
        }
        st.session_state.last_ai_summary = None
        st.session_state.last_ai_teaching = None
        st.session_state.last_ai_link = None
        st.session_state.skip_ids.discard(qid)

        if st.session_state.return_to_qid is not None:
            st.session_state.qid = st.session_state.return_to_qid
            st.session_state.return_to_qid = None
            st.session_state.phase = "question"
            st.session_state.self_rating = None
            st.rerun()
        else:
            st.session_state.round_index += 1
            if st.session_state.round_index >= st.session_state.round_size:
                st.session_state.round_phase = "summary"
                st.session_state.qid = None
                st.rerun()
            else:
                st.session_state.qid = None
                st.session_state.phase = "question"
                st.session_state.self_rating = None
                st.rerun()

    if st.session_state.qid is None:
        q = quiz_module.pick_next_question(
            session,
            chapter_filter=st.session_state.round_chapter,
            exclude_ids=set(e["qid"] for e in st.session_state.round_events),
            skip_ids=st.session_state.skip_ids,
        )
        if q is None:
            st.warning("没有可用题目，本轮结束。")
            st.session_state.round_phase = "summary"
            st.rerun()
        st.session_state.qid = q.id
        st.session_state.phase = "question"
        st.session_state.self_rating = None

    q = session.query(Question).filter(Question.id == st.session_state.qid).first()
    if q is None:
        st.session_state.qid = None
        st.rerun()

    # 侧栏
    with st.sidebar:
        st.markdown(f"### 📊 本轮进度")
        st.markdown(f"**{st.session_state.round_index} / {st.session_state.round_size}**")
        st.caption(f"范围：{st.session_state.round_chapter}")
        st.markdown("---")
        if st.button("⏹ 结束本轮", use_container_width=True):
            st.session_state.round_phase = "summary"
            st.rerun()
        if st.button("🔄 换一题", use_container_width=True):
            if st.session_state.qid:
                st.session_state.skip_ids.add(st.session_state.qid)
            st.session_state.qid = None
            st.session_state.phase = "question"
            st.session_state.self_rating = None
            st.rerun()
        st.caption(f"已跳过 {len(st.session_state.skip_ids)} 道")

    # 上一题 AI 诊断
    info = st.session_state.last_question_info
    if info:
        short = info["stem"][:40] + ("..." if len(info["stem"]) > 40 else "")
        with st.expander(f"🔍 上一题 AI 诊断（[{info.get('year','')}年] {short}）", expanded=False):
            st.caption(
                f"你上一题选的是「{info['self_rating'] or '—'}」，"
                f"错因「{info['error_type'] or '—'}」，"
                f"{'✅ 答对' if info['is_correct'] else '❌ 答错'}"
            )
            st.markdown(f"**上一题题干**：{info['stem']}")
            if info.get("kp_text"):
                st.markdown(f"**涉及知识点**：{info['kp_text']}")
            st.markdown("---")

            if info["is_correct"]:
                st.caption("这题答对了，不需要诊断。")
            else:
                if st.session_state.last_ai_summary is None:
                    if st.button("🔍 诊断错因 + 薄弱点", key="last_ai_btn1"):
                        with st.spinner("AI 老师分析中..."):
                            st.session_state.last_ai_summary = ai_module.diagnose_summary(
                                stem=info["stem"], answer=info["answer"],
                                kp_text=info["kp_text"],
                                self_rating=info["self_rating"],
                                error_type=info["error_type"])
                        st.rerun()

                if st.session_state.last_ai_summary:
                    r = st.session_state.last_ai_summary
                    with st.container(border=True):
                        if r.get("error_analysis"):
                            st.markdown(f"**🔍 错因分析**：{r['error_analysis']}")
                        if r.get("weak_points"):
                            st.markdown("**⚠️ 可能的薄弱知识点**")
                            for w in r["weak_points"]:
                                st.markdown(f"- {w}")
                        st.markdown("---")
                        c1, c2 = st.columns(2)
                        if c1.button("📖 看精讲 + 记忆技巧", key="last_ai_btn2",
                                     use_container_width=True):
                            with st.spinner("生成中..."):
                                st.session_state.last_ai_teaching = ai_module.diagnose_teaching(
                                    stem=info["stem"], answer=info["answer"],
                                    kp_text=info["kp_text"])
                            st.rerun()
                        if c2.button("🔀 易混 + 相近知识点", key="last_ai_btn3",
                                     use_container_width=True):
                            with st.spinner("生成中..."):
                                st.session_state.last_ai_link = ai_module.diagnose_link(
                                    stem=info["stem"], kp_text=info["kp_text"])
                            st.rerun()

                if st.session_state.last_ai_teaching:
                    r = st.session_state.last_ai_teaching
                    with st.container(border=True):
                        if r.get("explanation"):
                            st.markdown(f"**📖 知识点精讲**\n\n{r['explanation']}")
                        if r.get("memory_tips"):
                            st.info(f"💡 **记忆技巧**：{r['memory_tips']}")

                if st.session_state.last_ai_link:
                    r = st.session_state.last_ai_link
                    with st.container(border=True):
                        if r.get("confused_with"):
                            st.markdown("**🔀 容易混淆的概念**")
                            for c in r["confused_with"]:
                                st.markdown(f"- {c}")
                        if r.get("similar_kps"):
                            st.markdown("**🔗 相近知识点**：" + " / ".join(r["similar_kps"]))

                if st.session_state.phase == "question" and st.session_state.return_to_qid is None:
                    st.markdown("---")
                    if st.button("➕ 再做一道相同/相近知识点的题",
                                 use_container_width=True, key="do_similar"):
                        similar = quiz_module.find_similar_question(
                            session, source_qid=info["qid"],
                            exclude_ids=st.session_state.skip_ids,
                            chapter_fallback=settings.get("similar_by_chapter_fallback", False),
                            chapter_name=info.get("chapter"),
                        )
                        if similar is None:
                            st.warning("题库里没有找到相近的其他题目。可在设置里开启『按章节 fallback』。")
                        else:
                            st.session_state.return_to_qid = st.session_state.qid
                            st.session_state.qid = similar.id
                            st.session_state.phase = "question"
                            st.session_state.self_rating = None
                            st.rerun()
        st.markdown("---")

    # 当前题
    ri = (session.query(ReviewItem)
          .filter(ReviewItem.item_type == "question", ReviewItem.item_id == q.id).first())
    if st.session_state.return_to_qid:
        st.info("📎 这是补充练习。做完会自动返回原题。")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("章节", q.chapter_name or "—")
    col2.metric("年份", f"{q.year}年" if q.year else "—")
    col3.metric("复习次数", ri.reps if ri else 0)
    col4.metric("下次间隔", f"{ri.interval} 天" if ri else "—")

    st.markdown("---")
    st.markdown("### 📝 题干")
    st.markdown(f"**{q.stem}**")
    if q.kp_text:
        with st.expander("🔖 涉及知识点"):
            st.write(q.kp_text)

    if st.session_state.phase == "question":
        st.markdown("---")
        st.markdown("#### 先尝试回忆，再选择：")
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ 记得", use_container_width=True):
            st.session_state.self_rating = "记得"
            st.session_state.phase = "answer_confirm"
            st.rerun()
        if c2.button("🤔 模糊", use_container_width=True):
            st.session_state.self_rating = "模糊"
            st.session_state.phase = "answer_confirm"
            st.rerun()
        if c3.button("❌ 忘记了", use_container_width=True):
            st.session_state.self_rating = "忘记"
            st.session_state.phase = "error_select"
            st.rerun()

    if st.session_state.phase == "answer_confirm":
        st.markdown("---")
        st.markdown("### 💡 答案")
        st.markdown(q.answer or "（无答案）")
        st.markdown("---")
        st.markdown("#### 我刚才：")
        c1, c2 = st.columns(2)
        if c1.button("✅ 记对了", use_container_width=True):
            finish_question(q.id, correct=True, error_type=None)
        if c2.button("❌ 记错了 / 没理解", use_container_width=True):
            st.session_state.phase = "error_select"
            st.rerun()

    if st.session_state.phase == "error_select":
        st.markdown("---")
        st.markdown("### 💡 答案")
        st.markdown(q.answer or "（无答案）")
        st.markdown("---")
        st.markdown("#### 🩺 错因是？")
        error_options = ["记混了", "记错了", "没理解", "不会应用", "粗心"]
        cols = st.columns(len(error_options))
        chosen = None
        for i, opt in enumerate(error_options):
            if cols[i].button(opt, use_container_width=True, key=f"err_{opt}"):
                chosen = opt
        st.caption("💡 选完错因进入下一题，可点顶部「🔍 上一题 AI 诊断」查看详解")
        if chosen:
            finish_question(q.id, correct=False, error_type=chosen)

    st.stop()


# ========================================================
# 阶段 3：结尾
# ========================================================
if st.session_state.round_phase == "summary":
    st.title("🎉 本轮结束")

    events = st.session_state.round_events
    n = len(events)
    if n == 0:
        st.info("本轮没有做题记录。")
        if st.button("↩️ 回到封面", use_container_width=True):
            st.session_state.round_phase = "cover"
            st.rerun()
        st.stop()

    correct = sum(1 for e in events if e["is_correct"])
    wrong = n - correct
    acc = correct / n * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("本轮题数", n)
    c2.metric("正确", correct)
    c3.metric("错误", wrong)
    c4.metric("正确率", f"{acc:.1f}%")

    st.markdown("---")

    st.markdown("### 🧠 回忆自评分布")
    self_data = {
        "记得": sum(1 for e in events if e["self_rating"] == "记得"),
        "模糊": sum(1 for e in events if e["self_rating"] == "模糊"),
        "忘记": sum(1 for e in events if e["self_rating"] == "忘记"),
    }
    df = pd.DataFrame({"自评": list(self_data.keys()),
                       "次数": list(self_data.values())})
    base = alt.Chart(df).encode(
        x=alt.X("自评:N", axis=alt.Axis(labelAngle=0, title=None,
                                        labelFontSize=13, tickSize=0,
                                        domainColor="#666", labelColor="#ddd")),
        y=alt.Y("次数:Q", axis=alt.Axis(title=None, labelFontSize=13,
                                        tickSize=0, domainColor="#666",
                                        gridColor="#333", gridOpacity=0.3,
                                        labelColor="#ddd")),
    )
    bars = base.mark_bar(size=80, cornerRadius=6, color="#5B9BD5")
    labels = base.mark_text(dy=-10, fontSize=14, color="#ddd").encode(text="次数:Q")
    st.altair_chart((bars + labels).properties(height=280), use_container_width=True)

    err_data = {}
    for e in events:
        if e["is_correct"] is False and e["error_type"]:
            err_data[e["error_type"]] = err_data.get(e["error_type"], 0) + 1

    if err_data:
        with st.expander("🩺 错因占比", expanded=False):
            err_df = pd.DataFrame({"错因": list(err_data.keys()),
                                   "次数": list(err_data.values())})
            err_df = err_df.sort_values("次数", ascending=False)
            base = alt.Chart(err_df).encode(
                x=alt.X("错因:N", axis=alt.Axis(labelAngle=0, title=None,
                                                labelFontSize=13, tickSize=0,
                                                domainColor="#666", labelColor="#ddd"),
                        sort=err_df["错因"].tolist()),
                y=alt.Y("次数:Q", axis=alt.Axis(title=None, labelFontSize=13,
                                                tickSize=0, domainColor="#666",
                                                gridColor="#333", gridOpacity=0.3,
                                                labelColor="#ddd")),
            )
            bars = base.mark_bar(size=60, cornerRadius=6, color="#E06C75")
            labels = base.mark_text(dy=-10, fontSize=14, color="#ddd").encode(text="次数:Q")
            st.altair_chart((bars + labels).properties(height=260), use_container_width=True)

            st.markdown("**本轮错题列表**")
            for e in events:
                if e["is_correct"] is False:
                    with st.expander(f"[{e['year']}年] {e['stem'][:50]}..."):
                        st.markdown(f"**自评**：{e['self_rating']}")
                        st.markdown(f"**错因**：{e['error_type']}")

    st.markdown("---")

    if st.button("☕ 休息一下（回到封面）", type="primary", use_container_width=True):
        st.session_state.round_phase = "cover"
        st.session_state.round_events = []
        st.session_state.round_index = 0
        st.session_state.last_question_info = None
        st.session_state.last_ai_summary = None
        st.session_state.last_ai_teaching = None
        st.session_state.last_ai_link = None
        st.rerun()

    st.stop()