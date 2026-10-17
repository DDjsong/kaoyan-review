import os
import sys
import json
import random
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import altair as alt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, ReviewItem, StudyEvent, KnowledgePoint, QuestionKP, active_q_filter
from core import ai as ai_module
from core import quiz as quiz_module
from core.settings import load_settings

st.set_page_config(
    page_title="刷题",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

session = get_session()
settings = load_settings()

# ---------------- 状态 ----------------
for key, default in [
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
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ========================================================
# 阶段 1：封面
# ========================================================
if st.session_state.round_phase == "cover":
    st.title("📖 开始新一轮")

    round_size = int(settings.get("round_size", 20))

    from core.cache import get_chapters_cached, get_wrong_count_cached

    chapters = get_chapters_cached(session)
    chapters.sort()
    chapter_options = ["错题本", "全部章节"] + chapters

    wrong_qids_count = get_wrong_count_cached(session)

    # ---------- 年份列表（套卷模式） ----------
    year_rows = session.query(Question.year).filter(active_q_filter()).distinct().all()
    year_list = sorted([r[0] for r in year_rows if r[0]])
    year_options = ["不限年份"] + [f"{y} 年" for y in year_list]

    # ---------- 题型列表 ----------
    type_options = ["不限题型", "选择题", "判断题", "填空题", "名词解释", "问答题"]
    type_map = {"选择题": "选择", "判断题": "判断", "填空题": "填空", "名词解释": "名词解释", "问答题": "问答"}

    # ---------- 出题范围 + 年份 + 题型 + 本轮题数 并排 ----------
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])

    with c1:
        st.markdown("#### 📚 出题范围")
        default_idx = 1
        if st.session_state.round_chapter in chapter_options:
            default_idx = chapter_options.index(st.session_state.round_chapter)
        chapter_choice = st.selectbox(
            "选择范围", chapter_options,
            index=default_idx,
            key="cover_chapter",
            label_visibility="collapsed",
        )

    with c2:
        st.markdown("#### 🗓 年份（套卷）")
        default_year_idx = 0
        if st.session_state.round_year:
            label = f"{st.session_state.round_year} 年"
            if label in year_options:
                default_year_idx = year_options.index(label)
        year_choice_label = st.selectbox(
            "年份", year_options, index=default_year_idx,
            key="cover_year", label_visibility="collapsed",
        )
        year_choice = None if year_choice_label == "不限年份" else int(year_choice_label.replace(" 年", ""))

    with c3:
        st.markdown("#### 🏷 题型")
        default_type_idx = 0
        if st.session_state.round_type:
            for label, val in type_map.items():
                if val == st.session_state.round_type:
                    default_type_idx = type_options.index(label)
                    break
        type_choice_label = st.selectbox(
            "题型", type_options, index=default_type_idx,
            key="cover_type", label_visibility="collapsed",
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
            st.session_state.round_chapter = chapter_choice
            st.session_state.round_year = year_choice
            st.session_state.round_type = type_choice
            st.session_state.round_size = round_size
            # 预取本轮题目（一次性抽好，之后从内存取题，避免每次点击查库）
            questions = quiz_module.pick_questions_batch(
                session, round_size, chapter_choice, year_choice, type_choice
            )
            st.session_state.round_questions = [q.id for q in questions]
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
if st.session_state.round_phase == "quiz":
    st.title("📖 刷题")

    total = st.session_state.round_size
    done = st.session_state.round_index
    st.progress(done / total if total else 0, text=f"进度：{done} / {total}")


    def finish_question(qid, correct, error_type, note=None):
        session.add(StudyEvent(
            item_type="question", item_id=qid,
            self_rating=st.session_state.self_rating,
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
        st.session_state.round_events.append({
            "qid": qid, "stem": q_obj.stem, "year": q_obj.year,
            "chapter": q_obj.chapter_name,
            "self_rating": st.session_state.self_rating,
            "is_correct": correct, "error_type": error_type,
            "note": note,  # ← 新增
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
        st.session_state.pending_error_type = None  # ← 清空
        st.session_state.judge_result = None  # ← 清空判卷结果

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
            st.session_state.judge_result = {
                "user_answer": user_answer,
                "correct_answer": correct_answer,
            }
            st.session_state.phase = "error_select"
            st.rerun()


    if st.session_state.qid is None:
        retry_qid = st.session_state.get("retry_qid")
        if retry_qid is not None:
            st.session_state.qid = retry_qid
            st.session_state.retry_qid = None
        else:
            # 从预取的本轮题目列表取下一题（不查库，流畅度更高）
            idx = st.session_state.round_index
            qids = st.session_state.round_questions
            if idx < len(qids):
                st.session_state.qid = qids[idx]
            else:
                st.warning("没有可用题目，本轮结束。")
                st.session_state.round_phase = "summary"
                st.rerun()
        st.session_state.phase = "question"
        st.session_state.self_rating = None

    q = session.query(Question).filter(Question.id == st.session_state.qid).first()
    if q is None:
        st.session_state.qid = None
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
        st.markdown(f"**{st.session_state.round_index} / {st.session_state.round_size}**")
        st.caption(f"范围：{st.session_state.round_chapter}")
        st.markdown("---")
        if st.button("⏹ 结束本轮", use_container_width=True):
            st.session_state.round_phase = "summary"
            st.rerun()
        if st.button("🔄 换一题", use_container_width=True):
            st.session_state.round_index += 1  # 跳过当前题，看下一题
            st.session_state.qid = None
            st.session_state.phase = "question"
            st.session_state.self_rating = None
            st.session_state.judge_result = None
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
            elif not settings.get("ai_diagnose_enabled", True):
                st.caption("⚠️ AI 诊断已在设置中关闭。可在【⚙️ 设置 → AI 功能】中开启。")
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
    if (q.data_status or "正常") == "存疑":
        st.warning("⚠️ 本题答案存疑（待核对），仅供参考，请勿据此判断自己的薄弱点。")
    st.markdown(f"**{q.stem}**")
    if q.kp_text:
        with st.expander("🔖 涉及知识点"):
            st.write(q.kp_text)

    if st.session_state.phase == "question":
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
        if st.session_state.get("judge_result"):
            jr = st.session_state.judge_result
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
                st.session_state.pending_error_type = opt
                st.session_state.phase = "note_input"
                st.rerun()
        st.caption("💡 选完错因后可以写笔记")

    if st.session_state.phase == "note_input":
        st.markdown("---")
        st.markdown("### 💡 答案")
        if st.session_state.get("judge_result"):
            jr = st.session_state.judge_result
            st.success(f"正确答案：{jr['correct_answer']}")
            if q.explanation:
                with st.expander("📖 解析"):
                    st.write(q.explanation)
        else:
            st.markdown(q.answer or "（无答案）")

        st.markdown("---")
        st.markdown(f"**你的错因**：`{st.session_state.pending_error_type}`")
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
                error_type=st.session_state.pending_error_type,
                note=note.strip() if note.strip() else None,
            )
        if c2.button("⏭ 跳过笔记", use_container_width=True):
            finish_question(
                q.id, correct=False,
                error_type=st.session_state.pending_error_type,
                note=None,
            )
        if c3.button("↩️ 重选错因", use_container_width=True):
            st.session_state.pending_error_type = None
            st.session_state.phase = "error_select"
            st.rerun()

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
        st.session_state.round_phase = "cover"
        st.session_state.round_events = []
        st.session_state.round_index = 0
        st.session_state.last_question_info = None
        st.session_state.last_ai_summary = None
        st.session_state.last_ai_teaching = None
        st.session_state.last_ai_link = None
        st.rerun()

    st.stop()