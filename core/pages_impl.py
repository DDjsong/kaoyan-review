"""页面实现：把原 pages/*.py 的模块级代码改造成函数，供 st.navigation 调用。

每个「学习 / 错题本 / 总结」页面都接收 subject 参数（"生化" / "细胞"），
函数开头写入 st.session_state["subject"]，学习页的所有 round_* / qid / phase 等
状态统一用 subject 前缀隔离，避免生化与细胞互相串状态。
"""
import os
import sys
import json
import random
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO

import streamlit as st
import pandas as pd
import altair as alt
from sqlalchemy import desc, func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session, DB_PATH
from core.models import (
    Question, StudyEvent, ReviewItem, KnowledgePoint, QuestionKP, AIAdvice,
    active_q_filter,
)
from core import ai as ai_module
from core import quiz as quiz_module
from core.settings import load_settings, save_settings, get_chapter_importance

SUBJECTS = ["生化", "细胞"]

# ---------------------------------------------------------------------------
# 导航注册表：app.py 在 st.navigation 之前把「科目 -> 学习页 Page 对象」注册进来，
# 供错题本「立刻重做」用 st.switch_page(Page) 跳到对应科目的学习页。
# st.switch_page 对「函数页」只接受 Page 对象，不接受字符串路径。
# ---------------------------------------------------------------------------
_STUDY_PAGES = {}


def register_study_pages(mapping):
    """由 app.py 调用，注册 {subject: st.Page(study_page)} 映射。"""
    _STUDY_PAGES.update(mapping)


def _switch_to_study(subject):
    page = _STUDY_PAGES.get(subject)
    if page is not None:
        st.switch_page(page)
    else:
        # 兜底：理论上不会走到这里
        st.rerun()


# ========================================================
# 首页
# ========================================================
def home_page():
    st.markdown('<div class="hero-title">📚 考研专业课复习系统</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-subtitle">主动回忆 · 间隔重复 · AI 辅助 · 让背诵更高效</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4, gap="medium")

    with col1:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">📖</div>
            <div class="feature-title">刷题</div>
            <div class="feature-desc">
                按范围出题：全部 / 指定章节 / 错题本。<br>
                自评 → 看答案 → 校准 → 选错因。
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">📕</div>
            <div class="feature-title">错题本</div>
            <div class="feature-desc">
                自动记录错题，按知识点聚合。<br>
                按遗忘曲线安排复习。
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">📊</div>
            <div class="feature-title">总结</div>
            <div class="feature-desc">
                学习统计、自评分布、错因分析、<br>
                薄弱知识点、章节掌握度。
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown("""
        <div class="feature-card">
            <div class="feature-icon">🤖</div>
            <div class="feature-title">AI 老师</div>
            <div class="feature-desc">
                错因诊断 · 知识点精讲<br>
                记忆技巧 · 相近题推荐
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div class="footer-note">
        👈 从左侧选择页面开始使用
        <br><br>
        v0.1 · 数据源：现代生物化学真题
    </div>
    """, unsafe_allow_html=True)


# ========================================================
# 学习（刷题）
# ========================================================
def study_page(subject):
    st.session_state["subject"] = subject

    # ---- subject 前缀隔离：所有学习页状态都挂在 {subject}_ 前缀下 ----
    def skey(base):
        return f"{subject}_{base}"

    def ss(base, default=None):
        k = skey(base)
        if k not in st.session_state:
            st.session_state[k] = default
        return st.session_state[k]

    def sset(base, value):
        st.session_state[skey(base)] = value

    session = get_session()
    settings = load_settings()

    # ---------------- 状态 ----------------
    for base, default in [
        ("round_phase", "cover"),        # cover / quiz / summary
        ("round_size", settings.get("round_size", 20)),
        ("round_index", 0),
        ("round_events", []),
        ("round_chapter", "全部章节"),
        ("round_year", None),
        ("round_type", None),
        ("round_questions", []),
        ("retry_qid", None),
        ("qid", None),
        ("phase", "question"),           # question / answer_confirm / error_select
        ("self_rating", None),
        ("skip_ids", set()),
        ("return_to_qid", None),
        ("last_question_info", None),
        ("last_ai_summary", None),
        ("last_ai_teaching", None),
        ("last_ai_link", None),
        ("pending_error_type", None),
        ("judge_result", None),
    ]:
        ss(base, default)


    # ========================================================
    # 阶段 1：封面
    # ========================================================
    if ss("round_phase") == "cover":
        st.title("📖 开始新一轮")

        round_size = int(settings.get("round_size", 20))

        from core.cache import get_chapters_cached, get_wrong_count_cached

        chapters = get_chapters_cached(session, subject)
        chapters.sort()
        chapter_options = ["错题本", "全部章节"] + chapters

        wrong_qids_count = get_wrong_count_cached(session, subject)

        # ---------- 年份列表（套卷模式） ----------
        year_rows = session.query(Question.year).filter(active_q_filter(), Question.subject == subject).distinct().all()
        year_list = sorted([r[0] for r in year_rows if r[0]])
        year_options = ["不限年份"] + [f"{y} 年" for y in year_list]

        # ---------- 题型列表（按科目动态：细胞只有名词解释/问答） ----------
        if subject == "细胞":
            type_options = ["不限题型", "名词解释", "问答题"]
        else:
            type_options = ["不限题型", "选择题", "判断题", "填空题", "名词解释", "问答题"]
        type_map = {"选择题": "选择", "判断题": "判断", "填空题": "填空", "名词解释": "名词解释", "问答题": "问答"}

        # ---------- 出题范围 + 年份 + 题型 + 本轮题数 并排 ----------
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])

        with c1:
            st.markdown("#### 📚 出题范围")
            default_idx = 1
            if ss("round_chapter") in chapter_options:
                default_idx = chapter_options.index(ss("round_chapter"))
            chapter_choice = st.selectbox(
                "选择范围", chapter_options,
                index=default_idx,
                key=f"{subject}_cover_chapter",
                label_visibility="collapsed",
            )

        with c2:
            st.markdown("#### 🗓 年份（套卷）")
            default_year_idx = 0
            if ss("round_year"):
                label = f"{ss('round_year')} 年"
                if label in year_options:
                    default_year_idx = year_options.index(label)
            year_choice_label = st.selectbox(
                "年份", year_options, index=default_year_idx,
                key=f"{subject}_cover_year", label_visibility="collapsed",
            )
            year_choice = None if year_choice_label == "不限年份" else int(year_choice_label.replace(" 年", ""))

        with c3:
            st.markdown("#### 🏷 题型")
            default_type_idx = 0
            if ss("round_type"):
                for label, val in type_map.items():
                    if val == ss("round_type"):
                        default_type_idx = type_options.index(label)
                        break
            type_choice_label = st.selectbox(
                "题型", type_options, index=default_type_idx,
                key=f"{subject}_cover_type", label_visibility="collapsed",
            )
            type_choice = type_map.get(type_choice_label)

        with c4:
            st.markdown("#### 🔢 本轮题数")
            round_size = st.number_input(
                "题数", min_value=1, max_value=200, value=round_size,
                step=5, label_visibility="collapsed",
            )

        # ---------- 错题本提示 ----------
        if chapter_choice == "错题本":
            if wrong_qids_count == 0:
                st.warning("错题本里暂时没有题。先去刷几道，做错了才会进错题本。")
            else:
                st.success(f"📕 错题本中共有 **{wrong_qids_count}** 道题")

        st.caption("年份选「不限年份」时按加权抽题；选具体年份则按该年真题的题号顺序成套刷题。")

        # ---------- 开始按钮（放到显眼位置） ----------
        can_start = not (chapter_choice == "错题本" and wrong_qids_count == 0)

        if st.button("🚀 开始本轮", type="primary",
                     use_container_width=True, disabled=not can_start):
            with st.spinner("正在准备题目..."):
                sset("round_chapter", chapter_choice)
                sset("round_year", year_choice)
                sset("round_type", type_choice)
                sset("round_size", round_size)
                # 预取本轮题目（一次性抽好，之后从内存取题，避免每次点击查库）
                questions = quiz_module.pick_questions_batch(
                    session, round_size, chapter_choice, year_choice, type_choice,
                    subject_filter=subject,
                )
                sset("round_questions", [q.id for q in questions])
                sset("round_index", 0)
                sset("round_events", [])
                sset("qid", None)
                sset("phase", "question")
                sset("self_rating", None)
                sset("skip_ids", set())
                sset("return_to_qid", None)
                sset("last_question_info", None)
                sset("last_ai_summary", None)
                sset("last_ai_teaching", None)
                sset("last_ai_link", None)
                sset("round_phase", "quiz")
            st.rerun()
        # ---------- 抽题规则（默认收起） ----------
        st.markdown("---")
        with st.expander("🎯 抽题规则（点击展开）", expanded=False):
            if chapter_choice == "错题本":
                st.markdown(
                    "**错题本模式**：只从你做错过的题里抽，优先复习到期错题。\n\n"
                    "连续答对 3 次且间隔超过 30 天的题会**归档**，不再出现在错题本。"
                )
            else:
                st.markdown(
                    "系统按以下优先级加权抽题（自动排除本轮已做、已跳过的题）：\n\n"
                    "1. **50%** 到期复习题（错题、学过的题）\n"
                    "2. **25%** 高权重知识点题目（重点知识点）\n"
                    "3. **15%** 新题（从未做过）\n"
                    "4. **10%** 其他随机\n\n"
                    "在【设置 → 重点权重】里调整章节/知识点权重，会影响抽取。"
                )

        st.stop()


    # ========================================================
    # 阶段 2：做题
    # ========================================================
    if ss("round_phase") == "quiz":
        st.title("📖 刷题")

        total = ss("round_size")
        done = ss("round_index")
        st.progress(done / total if total else 0, text=f"进度：{done} / {total}")


        def finish_question(qid, correct, error_type, note=None):
            session.add(StudyEvent(
                item_type="question", item_id=qid,
                self_rating=ss("self_rating"),
                is_correct=correct, error_type=error_type,
                note=note,  # ← 新增
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
                base_interval = max(1, int(ri.interval * ri.ease)) if ri.interval > 0 else 1
                # ±10% 随机抖动，避免同批题集中在同一天到期（复习雪崩）
                ri.interval = max(1, int(base_interval * random.uniform(0.9, 1.1)))
                ri.ease = min(2.5, ri.ease + 0.1)
                ri.state = "archived" if (ri.reps >= 4 and ri.interval >= 21) else "review"
            else:
                ri.reps = 0
                ri.interval = 1
                ri.ease = max(1.3, ri.ease - 0.2)
                ri.state = "learning"
            ri.due = datetime.now() + timedelta(days=ri.interval)
            session.commit()

            q_obj = session.query(Question).filter(Question.id == qid).first()
            ss("round_events").append({
                "qid": qid, "stem": q_obj.stem, "year": q_obj.year,
                "chapter": q_obj.chapter_name,
                "self_rating": ss("self_rating"),
                "is_correct": correct, "error_type": error_type,
                "note": note,  # ← 新增
            })
            sset("last_question_info", {
                "qid": qid, "stem": q_obj.stem, "answer": q_obj.answer,
                "kp_text": q_obj.kp_text, "year": q_obj.year,
                "chapter": q_obj.chapter_name,
                "self_rating": ss("self_rating"),
                "error_type": error_type, "is_correct": correct,
            })
            sset("last_ai_summary", None)
            sset("last_ai_teaching", None)
            sset("last_ai_link", None)
            ss("skip_ids").discard(qid)
            sset("pending_error_type", None)  # ← 清空
            sset("judge_result", None)        # ← 清空判卷结果

            if ss("return_to_qid") is not None:
                sset("qid", ss("return_to_qid"))
                sset("return_to_qid", None)
                sset("phase", "question")
                sset("self_rating", None)
                st.rerun()
            else:
                sset("round_index", ss("round_index") + 1)
                if ss("round_index") >= ss("round_size"):
                    sset("round_phase", "summary")
                    sset("qid", None)
                    st.rerun()
                else:
                    sset("qid", None)
                    sset("phase", "question")
                    sset("self_rating", None)
                    st.rerun()


        def _check_blank(correct, user):
            """填空题模糊匹配判卷：多空用「；」分隔，同义词用「/」分隔，括号为注释。"""
            import re
            def norm(s):
                if not s:
                    return ""
                s = s.strip().lower()
                s = re.sub(r"\s+", "", s)
                s = s.translate(str.maketrans("，；：（）", ",;:()"))
                return s
            c = norm(correct)
            u = norm(user)
            if not u:
                return False
            blanks = [b for b in c.split(";") if b] or [c]
            for b in blanks:
                candidates = [re.sub(r"[（(].*?[)）]", "", x) or x for x in b.split("/") if x]
                if not any(x in u for x in candidates):
                    return False
            return True


        def _judge_objective(q, user_answer, is_blank=False):
            """客观题判卷：答对直接记录并进入下一题；答错记录判卷结果并进入错因选择。"""
            correct_answer = (q.answer or "").strip()
            if is_blank:
                user_is_correct = _check_blank(correct_answer, user_answer)
            elif q.question_type == "判断":
                user_is_correct = (user_answer == correct_answer)
            else:
                user_is_correct = (user_answer.upper() == correct_answer.upper())
            if user_is_correct:
                finish_question(q.id, correct=True, error_type=None)
            else:
                sset("judge_result", {
                    "user_answer": user_answer,
                    "correct_answer": correct_answer,
                })
                sset("phase", "error_select")
                st.rerun()


        def show_kp_info(q):
            """展示知识点定位/重点/考点/考频（答案放在这些信息下面）"""
            parts = []
            if q.kp_text:
                parts.append(f"**📌 知识点**：{q.kp_text}")
            if q.kp_location:
                parts.append(f"**📍 章节定位**：{q.kp_location}")
            if q.kp_key_point:
                parts.append(f"**⭐ 重点**：{q.kp_key_point}")
            if q.kp_exam_point:
                parts.append(f"**🎯 考点**：{q.kp_exam_point}")
            if q.kp_frequency:
                parts.append(f"**📊 考频**：{q.kp_frequency}")
            if parts:
                st.markdown("---")
                st.markdown("### 📚 知识点详解")
                for p in parts:
                    st.markdown(p)


        if ss("qid") is None:
            retry_qid = ss("retry_qid")
            if retry_qid is not None:
                sset("qid", retry_qid)
                sset("retry_qid", None)
            else:
                # 从预取的本轮题目列表取下一题（不查库，流畅度更高）
                idx = ss("round_index")
                qids = ss("round_questions")
                if idx < len(qids):
                    sset("qid", qids[idx])
                else:
                    st.warning("没有可用题目，本轮结束。")
                    sset("round_phase", "summary")
                    st.rerun()
            sset("phase", "question")
            sset("self_rating", None)

        q = session.query(Question).filter(Question.id == ss("qid")).first()
        if q is None:
            sset("qid", None)
            st.rerun()

        # 题型判断（answer_mode 分流）
        qtype = (q.question_type or "").strip()
        options_dict = {}
        if q.options:
            try:
                _o = json.loads(q.options) if isinstance(q.options, str) else q.options
                options_dict = _o if isinstance(_o, dict) else {}
            except Exception:
                options_dict = {}
        is_judge = qtype == "判断"
        is_choice = qtype == "选择" and bool(options_dict)
        is_blank = qtype == "填空"
        is_self = not (is_judge or is_choice or is_blank)

        # 侧栏
        with st.sidebar:
            st.markdown(f"### 📊 本轮进度")
            st.markdown(f"**{ss('round_index')} / {ss('round_size')}**")
            st.caption(f"范围：{ss('round_chapter')}")
            st.markdown("---")
            if st.button("⏹ 结束本轮", use_container_width=True):
                sset("round_phase", "summary")
                st.rerun()
            if st.button("🔄 换一题", use_container_width=True):
                sset("round_index", ss("round_index") + 1)  # 跳过当前题，看下一题
                sset("qid", None)
                sset("phase", "question")
                sset("self_rating", None)
                sset("judge_result", None)
                st.rerun()
            st.caption(f"已跳过 {len(ss('skip_ids'))} 道")

        # 上一题 AI 诊断
        info = ss("last_question_info")
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
                elif not settings.get("ai_diagnose_enabled", True):
                    st.caption("⚠️ AI 诊断已在设置中关闭。可在【⚙️ 设置 → AI 功能】中开启。")
                else:
                    if ss("last_ai_summary") is None:
                        if st.button("🔍 诊断错因 + 薄弱点", key="last_ai_btn1"):
                            with st.spinner("AI 老师分析中..."):
                                sset("last_ai_summary", ai_module.diagnose_summary(
                                    stem=info["stem"], answer=info["answer"],
                                    kp_text=info["kp_text"],
                                    self_rating=info["self_rating"],
                                    error_type=info["error_type"]))
                            st.rerun()

                    if ss("last_ai_summary"):
                        r = ss("last_ai_summary")
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
                                    sset("last_ai_teaching", ai_module.diagnose_teaching(
                                        stem=info["stem"], answer=info["answer"],
                                        kp_text=info["kp_text"]))
                                st.rerun()
                            if c2.button("🔀 易混 + 相近知识点", key="last_ai_btn3",
                                         use_container_width=True):
                                with st.spinner("生成中..."):
                                    sset("last_ai_link", ai_module.diagnose_link(
                                        stem=info["stem"], kp_text=info["kp_text"]))
                                st.rerun()

                    if ss("last_ai_teaching"):
                        r = ss("last_ai_teaching")
                        with st.container(border=True):
                            if r.get("explanation"):
                                st.markdown(f"**📖 知识点精讲**\n\n{r['explanation']}")
                            if r.get("memory_tips"):
                                st.info(f"💡 **记忆技巧**：{r['memory_tips']}")

                    if ss("last_ai_link"):
                        r = ss("last_ai_link")
                        with st.container(border=True):
                            if r.get("confused_with"):
                                st.markdown("**🔀 容易混淆的概念**")
                                for c in r["confused_with"]:
                                    st.markdown(f"- {c}")
                            if r.get("similar_kps"):
                                st.markdown("**🔗 相近知识点**：" + " / ".join(r["similar_kps"]))

                    if ss("phase") == "question" and ss("return_to_qid") is None:
                        st.markdown("---")
                        if st.button("➕ 再做一道相同/相近知识点的题",
                                     use_container_width=True, key="do_similar"):
                            similar = quiz_module.find_similar_question(
                                session, source_qid=info["qid"],
                                exclude_ids=ss("skip_ids"),
                                chapter_fallback=settings.get("similar_by_chapter_fallback", False),
                                chapter_name=info.get("chapter"),
                            )
                            if similar is None:
                                st.warning("题库里没有找到相近的其他题目。可在设置里开启『按章节 fallback』。")
                            else:
                                sset("return_to_qid", ss("qid"))
                                sset("qid", similar.id)
                                sset("phase", "question")
                                sset("self_rating", None)
                                st.rerun()
            st.markdown("---")

        # 当前题
        ri = (session.query(ReviewItem)
              .filter(ReviewItem.item_type == "question", ReviewItem.item_id == q.id).first())
        if ss("return_to_qid"):
            st.info("📎 这是补充练习。做完会自动返回原题。")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("章节", q.chapter_name or "—")
        col2.metric("年份", f"{q.year}年" if q.year else "—")
        col3.metric("复习次数", ri.reps if ri else 0)
        col4.metric("下次间隔", f"{ri.interval} 天" if ri else "—")

        st.markdown("---")
        st.markdown("### 📝 题干")
        if (q.data_status or "正常") == "存疑":
            st.warning("⚠️ 本题答案存疑（待核对），仅供参考，请勿据此判断自己的薄弱点。")
        st.markdown(f"**{q.stem}**")
        if q.kp_text:
            with st.expander("🔖 涉及知识点"):
                st.write(q.kp_text)

        if ss("phase") == "question":
            st.markdown("---")
            if is_judge:
                st.markdown("#### ⚖️ 判断对错：")
                c1, c2 = st.columns(2)
                if c1.button("✅ 正确（√）", use_container_width=True, key=f"judge_t_{q.id}"):
                    _judge_objective(q, user_answer="√")
                if c2.button("❌ 错误（×）", use_container_width=True, key=f"judge_f_{q.id}"):
                    _judge_objective(q, user_answer="×")
            elif is_choice:
                st.markdown("#### 🔘 请选择：")
                for key in ["A", "B", "C", "D"]:
                    if key in options_dict:
                        if st.button(f"**{key}**. {options_dict[key]}",
                                     use_container_width=True, key=f"opt_{q.id}_{key}"):
                            _judge_objective(q, user_answer=key)
            elif is_blank:
                st.markdown("#### ✍️ 填写答案：")
                st.caption("多个空用「；」分隔，同义词可任填其一")
                user_ans = st.text_input("答案", key=f"blank_{q.id}", placeholder="在此输入答案")
                if st.button("✅ 提交答案", type="primary", use_container_width=True, key=f"blank_submit_{q.id}"):
                    _judge_objective(q, user_answer=user_ans, is_blank=True)
            else:
                st.markdown("#### 先尝试回忆，再选择：")
                c1, c2, c3 = st.columns(3)
                if c1.button("✅ 记得", use_container_width=True):
                    sset("self_rating", "记得")
                    sset("phase", "answer_confirm")
                    st.rerun()
                if c2.button("🤔 模糊", use_container_width=True):
                    sset("self_rating", "模糊")
                    sset("phase", "answer_confirm")
                    st.rerun()
                if c3.button("❌ 忘记了", use_container_width=True):
                    sset("self_rating", "忘记")
                    sset("phase", "error_select")
                    st.rerun()

        if ss("phase") == "answer_confirm":
            st.markdown("---")
            show_kp_info(q)
            st.markdown("### 💡 答案")
            st.markdown(q.answer or "（无答案）")
            st.markdown("---")
            st.markdown("#### 我刚才：")
            c1, c2 = st.columns(2)
            if c1.button("✅ 记对了", use_container_width=True):
                finish_question(q.id, correct=True, error_type=None)
            if c2.button("❌ 记错了 / 没理解", use_container_width=True):
                sset("phase", "error_select")
                st.rerun()

        if ss("phase") == "error_select":
            st.markdown("---")
            show_kp_info(q)
            st.markdown("### 💡 答案")
            if ss("judge_result"):
                jr = ss("judge_result")
                st.error(f"你的答案：{jr['user_answer'] or '（未作答）'}")
                st.success(f"正确答案：{jr['correct_answer']}")
                if q.explanation:
                    with st.expander("📖 解析"):
                        st.write(q.explanation)
            else:
                st.markdown(q.answer or "（无答案）")
            st.markdown("---")
            st.markdown("#### 🩺 错因是？")
            error_options = ["记混了", "记错了", "没理解", "不会应用", "粗心"]
            cols = st.columns(len(error_options))
            for i, opt in enumerate(error_options):
                if cols[i].button(opt, use_container_width=True, key=f"err_{opt}"):
                    sset("pending_error_type", opt)
                    sset("phase", "note_input")
                    st.rerun()
            st.caption("💡 选完错因后可以写笔记")

        if ss("phase") == "note_input":
            st.markdown("---")
            show_kp_info(q)
            st.markdown("### 💡 答案")
            if ss("judge_result"):
                jr = ss("judge_result")
                st.success(f"正确答案：{jr['correct_answer']}")
                if q.explanation:
                    with st.expander("📖 解析"):
                        st.write(q.explanation)
            else:
                st.markdown(q.answer or "（无答案）")

            st.markdown("---")
            st.markdown(f"**你的错因**：`{ss('pending_error_type')}`")
            st.markdown("#### 📝 写点笔记（可选）")
            st.caption("记录理解、易错点、记忆方法等。下次做错题时能看到。")

            note = st.text_area(
                "笔记内容",
                key=f"note_area_{q.id}",
                height=150,
                placeholder="例如：DNA 连接酶负责连接缺口（磷酸二酯键），DNA 聚合酶负责填补缺口，二者容易混淆。",
                label_visibility="collapsed",
            )

            c1, c2, c3 = st.columns([2, 2, 1])
            if c1.button("💾 保存并继续", type="primary", use_container_width=True):
                finish_question(
                    q.id, correct=False,
                    error_type=ss("pending_error_type"),
                    note=note.strip() if note.strip() else None,
                )
            if c2.button("⏭ 跳过笔记", use_container_width=True):
                finish_question(
                    q.id, correct=False,
                    error_type=ss("pending_error_type"),
                    note=None,
                )
            if c3.button("↩️ 重选错因", use_container_width=True):
                sset("pending_error_type", None)
                sset("phase", "error_select")
                st.rerun()

        st.stop()


    # ========================================================
    # 阶段 3：结尾
    # ========================================================
    if ss("round_phase") == "summary":
        st.title("🎉 本轮结束")

        events = ss("round_events")
        n = len(events)
        if n == 0:
            st.info("本轮没有做题记录。")
            if st.button("↩️ 回到封面", use_container_width=True):
                sset("round_phase", "cover")
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
                                            domainColor="#94a3b8", labelColor="#334155")),
            y=alt.Y("次数:Q", axis=alt.Axis(title=None, labelFontSize=13,
                                            tickSize=0, domainColor="#94a3b8",
                                            gridColor="#e2e8f0", gridOpacity=0.6,
                                            labelColor="#334155")),
        )
        bars = base.mark_bar(size=80, cornerRadius=6, color="#4A90E2")
        labels = base.mark_text(dy=-10, fontSize=14, color="#334155").encode(text="次数:Q")
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
                                                    domainColor="#94a3b8", labelColor="#334155"),
                            sort=err_df["错因"].tolist()),
                    y=alt.Y("次数:Q", axis=alt.Axis(title=None, labelFontSize=13,
                                                    tickSize=0, domainColor="#94a3b8",
                                                    gridColor="#e2e8f0", gridOpacity=0.6,
                                                    labelColor="#334155")),
                )
                bars = base.mark_bar(size=60, cornerRadius=6, color="#E06C75")
                labels = base.mark_text(dy=-10, fontSize=14, color="#334155").encode(text="次数:Q")
                st.altair_chart((bars + labels).properties(height=260), use_container_width=True)

                st.markdown("**本轮错题列表**")
                for e in events:
                    if e["is_correct"] is False:
                        with st.expander(f"[{e['year']}年] {e['stem'][:50]}..."):
                            st.markdown(f"**自评**：{e['self_rating']}")
                            st.markdown(f"**错因**：{e['error_type']}")

        st.markdown("---")

        if st.button("☕ 休息一下（回到封面）", type="primary", use_container_width=True):
            sset("round_phase", "cover")
            sset("round_events", [])
            sset("round_index", 0)
            sset("last_question_info", None)
            sset("last_ai_summary", None)
            sset("last_ai_teaching", None)
            sset("last_ai_link", None)
            st.rerun()

        st.stop()


# ========================================================
# 错题本
# ========================================================
def wrong_page(subject):
    st.session_state["subject"] = subject
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

    # 取出这些题目 + 对应的复习项（排除已停用题）
    rows = (
        session.query(Question, ReviewItem)
        .join(ReviewItem, (ReviewItem.item_type == "question") & (ReviewItem.item_id == Question.id))
        .filter(Question.id.in_(error_qids))
        .filter(Question.subject == subject)
        .filter(active_q_filter())
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
                    if last_evt and last_evt.note:
                        st.info(f"📝 **我的笔记**：{last_evt.note}")
                    col2.metric("复习次数", ri.reps)
                    col3.metric("下次复习", ri.due.strftime("%m-%d") if ri.due else "—")
                    col4.metric("当前间隔", f"{ri.interval} 天")

                    c_act1, c_act2 = st.columns(2)
                    if c_act1.button(f"🔁 立刻重做", key=f"retry_{q.id}", use_container_width=True):
                        # 以 subject 前缀写入学习页状态，再切到「本科目」的学习页
                        st.session_state[f"{subject}_retry_qid"] = q.id
                        st.session_state[f"{subject}_round_phase"] = "quiz"
                        st.session_state[f"{subject}_round_index"] = 0
                        st.session_state[f"{subject}_round_events"] = []
                        st.session_state[f"{subject}_round_chapter"] = "错题本"
                        st.session_state[f"{subject}_round_year"] = None
                        st.session_state[f"{subject}_round_size"] = 1
                        st.session_state[f"{subject}_qid"] = None
                        st.session_state[f"{subject}_phase"] = "question"
                        st.session_state[f"{subject}_self_rating"] = None
                        st.session_state[f"{subject}_skip_ids"] = set()
                        st.session_state[f"{subject}_return_to_qid"] = None
                        st.session_state[f"{subject}_last_question_info"] = None
                        _switch_to_study(subject)
                    if c_act2.button(f"📦 手动归档", key=f"arch_{q.id}", use_container_width=True):
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


# ========================================================
# 总结
# ========================================================
def summary_page(subject):
    st.session_state["subject"] = subject
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

    # 排除「已停用」题目和其他科目的做题记录
    _active_qids = set(
        r[0] for r in session.query(Question.id)
        .filter(active_q_filter(), Question.subject == subject).all()
    )
    events = [e for e in events if e.item_id in _active_qids]

    if not events:
        st.info("所选时间范围内还没有学习记录。去刷题吧！")
        st.stop()

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

    # 通用 Altair 样式（浅色背景适用）
    AXIS_STYLE = dict(
        labelFontSize=13,
        titleFontSize=13,
        tickSize=0,
        domainColor="#94a3b8",
        domainWidth=1,
        gridColor="#e2e8f0",
        gridOpacity=0.6,
        labelColor="#334155",
        titleColor="#334155",
    )

    LABEL_COLOR = "#334155"
    BLUE = "#4A90E2"
    RED = "#E06C75"


    # ---------------- 回忆自评分布 ----------------
    st.markdown("### 🧠 回忆自评分布")
    self_counts = {
        "remember": sum(1 for e in events if e.self_rating == "remember"),
        "fuzzy": sum(1 for e in events if e.self_rating == "fuzzy"),
        "forgot": sum(1 for e in events if e.self_rating == "forgot"),
    }
    # 兼容中文自评（旧数据可能存的是中文）
    self_counts["remember"] += sum(1 for e in events if e.self_rating == "记得")
    self_counts["fuzzy"] += sum(1 for e in events if e.self_rating == "模糊")
    self_counts["forgot"] += sum(1 for e in events if e.self_rating == "忘记")

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
        y=alt.Y("次数:Q", axis=alt.Axis(title=None, **AXIS_STYLE)),
    )
    bars = base.mark_bar(size=80, cornerRadius=6, color=BLUE)
    labels = base.mark_text(dy=-10, fontSize=14, color=LABEL_COLOR, fontWeight="bold").encode(text="次数:Q")
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
            y=alt.Y("次数:Q", axis=alt.Axis(title=None, **AXIS_STYLE)),
        )
        bars = base.mark_bar(size=80, cornerRadius=6, color=RED)
        labels = base.mark_text(dy=-10, fontSize=14, color=LABEL_COLOR, fontWeight="bold").encode(text="次数:Q")
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
    st.caption("掌握度 = 该章做对的题数 ÷ 该章总题数，综合了正确率与刷题完成度")

    # 每章总题数（排除停用题）
    chapter_totals = dict(
        session.query(Question.chapter_name, func.count())
        .filter(active_q_filter())
        .group_by(Question.chapter_name)
        .all()
    )

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
            n_total = chapter_totals.get(ch, 0)
            acc = s["correct"] / s["total"] * 100 if s["total"] else 0
            completion = s["total"] / n_total * 100 if n_total else 0
            mastery = s["correct"] / n_total * 100 if n_total else 0
            chapter_rows.append({
                "章节": ch,
                "做题数": s["total"],
                "总题数": n_total,
                "正确率": round(acc, 1),
                "完成度": round(completion, 1),
                "掌握度": round(mastery, 1),
            })
        chapter_df = pd.DataFrame(chapter_rows).sort_values("掌握度")

        bars = alt.Chart(chapter_df).mark_bar(size=24, cornerRadius=6, color=BLUE).encode(
            y=alt.Y(
                "章节:N",
                axis=alt.Axis(title=None, **AXIS_STYLE),
                sort=chapter_df["章节"].tolist(),
            ),
            x=alt.X(
                "掌握度:Q",
                axis=alt.Axis(title="掌握度 (%)", **AXIS_STYLE),
                scale=alt.Scale(domain=[0, 100]),
            ),
            tooltip=["章节", "做题数", "总题数", "正确率", "完成度", "掌握度"],
        )
        labels = alt.Chart(chapter_df).mark_text(
            align="left", dx=6, fontSize=13, color=LABEL_COLOR, fontWeight="bold"
        ).encode(
            y=alt.Y("章节:N", sort=chapter_df["章节"].tolist()),
            x=alt.X("掌握度:Q"),
            text=alt.Text("掌握度:Q", format=".1f"),
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


# ========================================================
# AI 老师
# ========================================================
def ai_page():
    st.title("🤖 AI 老师")
    st.caption("基于你所有做题记录的整体诊断，越用越懂你")

    session = get_session()

    # 科目切换
    if "ai_subject" not in st.session_state:
        st.session_state.ai_subject = "生化"
    subject = st.radio("科目", ["生化", "细胞"], horizontal=True, key="ai_subject")


    # ---------- 1. 收集数据 ----------
    events = session.query(StudyEvent).filter(StudyEvent.item_type == "question").all()

    # 排除「已停用」和其他科目的做题记录，避免污染 AI 诊断
    _active_qids = set(
        r[0] for r in session.query(Question.id)
        .filter(func.coalesce(Question.data_status, "正常") != "停用")
        .filter(Question.subject == subject).all()
    )
    events = [e for e in events if e.item_id in _active_qids]

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

        # 最近 10 道错题（含题干、答案、解析；批量查询避免 N+1）
        recent_wrong_events = (
            session.query(StudyEvent)
            .filter(StudyEvent.item_type == "question", StudyEvent.is_correct == False)
            .filter(StudyEvent.item_id.in_(_active_qids))
            .order_by(StudyEvent.created_at.desc())
            .limit(10).all()
        )
        if recent_wrong_events:
            wrong_qids = [e.item_id for e in recent_wrong_events]
            q_map = {q.id: q for q in session.query(Question).filter(Question.id.in_(wrong_qids)).all()}
            lines.append("\n最近 10 道错题（题干 + 正确答案 + 解析）：")
            for e in recent_wrong_events:
                q = q_map.get(e.item_id)
                if not q:
                    continue
                line = f"  - [{q.year}年] 题干：{q.stem[:70]}"
                line += f" | 正确答案：{(q.answer or '')[:50]}"
                if q.explanation:
                    line += f" | 解析：{q.explanation[:80]}"
                line += f" | 错因：{e.error_type or '未选'}"
                lines.append(line)

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
    settings = load_settings()
    if not settings.get("ai_overall_enabled", True):
        st.info("⚠️ AI 老师分析已在设置中关闭。可在【⚙️ 设置 → AI 功能】中开启。")
    elif st.button("🧠 让 AI 老师分析我现在的状态", type="primary"):
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

    # ========================================================
    # AI 对话（追加在文件末尾）
    # ========================================================
    st.markdown("---")
    st.markdown("### 💬 和 AI 老师对话")
    st.caption("AI 已经了解你的全部做题数据、错题、笔记，可以直接问它任何问题")

    # 初始化对话历史
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 快捷问题
    st.markdown("**💡 试试问：**")
    quick_cols = st.columns(4)
    quick_questions = [
        "我最近哪里最弱？",
        "帮我分析一下错因",
        "给出接下来一周复习计划",
        "怎么理解错配修复？",
    ]
    for i, qq in enumerate(quick_questions):
        if quick_cols[i].button(qq, use_container_width=True, key=f"quick_{i}"):
            st.session_state.chat_history.append({"role": "user", "content": qq})
            st.session_state.chat_pending = True
            st.rerun()

    # 显示历史消息
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 处理"待回复"状态
    if st.session_state.get("chat_pending"):
        with st.chat_message("assistant"):
            with st.spinner("AI 老师思考中..."):
                try:
                    reply = ai_module.chat_with_ai(
                        session,
                        st.session_state.chat_history[-1]["content"],
                        st.session_state.chat_history[:-1],
                        subject=subject,
                    )
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": reply}
                    )
                except Exception as e:
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": f"⚠️ 出错了：{e}"}
                    )
        st.session_state.chat_pending = False
        st.rerun()

    # 输入框
    user_input = st.chat_input("输入你的问题...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.chat_pending = True
        st.rerun()

    # 清空对话
    if st.session_state.chat_history:
        if st.button("🗑 清空对话", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()


# ========================================================
# 设置
# ========================================================
def settings_page():
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
            r[0] for r in session.query(Question.chapter_name)
            .filter(active_q_filter()).distinct().all()
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
                        key=f"kp_slider_{chap}_{kp.id}",
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
        c1.metric("题目", session.query(Question).filter(active_q_filter()).count())
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
                "题号": q.question_no, "题型": q.question_type,
                "题干": q.stem, "答案": q.answer, "知识点": q.kp_text,
                "状态": q.data_status or "正常",
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
                    # 重新创建所有复习项（只针对未停用题）
                    for (qid,) in session.query(Question.id).filter(active_q_filter()).all():
                        session.add(ReviewItem(item_type="question", item_id=qid))
                    session.commit()
                    st.success("已清空学习记录")
                    st.rerun()
                else:
                    st.error("请输入 DELETE")
