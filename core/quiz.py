import random
from datetime import datetime
from sqlalchemy import func
import streamlit as st
from core.models import Question, ReviewItem, StudyEvent, KnowledgePoint, QuestionKP
from core.settings import get_chapter_importance


# 统一的"未停用"过滤条件（coalesce 兜底 NULL，老数据也当正常）
def _active_filter():
    return func.coalesce(Question.data_status, "正常") != "停用"


def pick_next_question(session, chapter_filter, exclude_ids, skip_ids, year_filter=None):
    """加权抽题。查询已优化为批量，避免逐题查库。"""
    now = datetime.now()
    exclude = set(exclude_ids) | set(skip_ids)

    # ============ 错题本模式 ============
    if chapter_filter == "错题本":
        wrong_qids = list(set(
            r[0] for r in
            session.query(StudyEvent.item_id)
            .filter(StudyEvent.item_type == "question",
                    StudyEvent.is_correct == False)
            .distinct().all()
        ))
        if year_filter:
            year_qids = set(
                r[0] for r in session.query(Question.id)
                .filter(Question.year == year_filter).all()
            )
            wrong_qids = [qid for qid in wrong_qids if qid in year_qids]
        if not wrong_qids:
            return None

        candidates = [qid for qid in wrong_qids if qid not in exclude]
        if not candidates:
            candidates = wrong_qids

        # 一次查询：找出到期的错题
        due_ris = (session.query(ReviewItem)
                   .filter(ReviewItem.item_type == "question",
                           ReviewItem.item_id.in_(candidates),
                           ReviewItem.due <= now,
                           ReviewItem.state != "archived")
                   .order_by(ReviewItem.due).limit(1).all())

        if due_ris:
            chosen_id = due_ris[0].item_id
        else:
            chosen_id = random.choice(candidates)

        return (session.query(Question)
                .filter(Question.id == chosen_id, _active_filter())
                .first())

    # ============ 套卷模式（按年份 + 题号顺序） ============
    if year_filter and chapter_filter != "错题本":
        qq = (session.query(Question)
              .filter(_active_filter(), Question.year == year_filter)
              .filter(~Question.id.in_(exclude)))
        if chapter_filter != "全部章节":
            qq = qq.filter(Question.chapter_name == chapter_filter)
        return qq.order_by(Question.question_no, Question.id).first()

    # ============ 普通模式 ============
    # 1) 一次查询：所有做过的题
    done_qids = set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question")
        .distinct().all()
    )

    # 2) 一次查询：候选题目（已排除停用题）
    all_q = session.query(Question).filter(_active_filter())
    if chapter_filter != "全部章节":
        all_q = all_q.filter(Question.chapter_name == chapter_filter)
    if year_filter:
        all_q = all_q.filter(Question.year == year_filter)
    all_candidates = all_q.all()
    if not all_candidates:
        return None

    qid_list = [q.id for q in all_candidates]
    q_map = {q.id: q for q in all_candidates}

    # 3) 一次查询：所有题目的知识点权重
    kp_importance_map = {}
    if qid_list:
        rows = (session.query(QuestionKP.question_id, KnowledgePoint.importance)
                .join(KnowledgePoint, KnowledgePoint.id == QuestionKP.kp_id)
                .filter(QuestionKP.question_id.in_(qid_list))
                .all())
        for qid, imp in rows:
            kp_importance_map[qid] = max(kp_importance_map.get(qid, 0), imp or 3)

    # 4) 一次查询：所有到期的 review_item
    due_qid_set = set()
    due_rows = (session.query(ReviewItem.item_id)
                .filter(ReviewItem.item_type == "question",
                        ReviewItem.due <= now,
                        ReviewItem.state != "archived")
                .all())
    for (qid,) in due_rows:
        due_qid_set.add(qid)

    # 5) 章节权重缓存
    chapter_imp_cache = {}

    def get_chap_w(chap_name):
        if chap_name not in chapter_imp_cache:
            chapter_imp_cache[chap_name] = (
                get_chapter_importance(chap_name) if chap_name else 3
            )
        return chapter_imp_cache[chap_name]

    # 6) 分池（全内存计算）
    due_qids = []
    high_weight_qids = []
    new_qids = []
    valid_qids = []

    for q in all_candidates:
        if q.id in exclude:
            continue
        valid_qids.append(q.id)
        if q.id in due_qid_set:
            due_qids.append(q.id)
        if kp_importance_map.get(q.id, 3) >= 4:
            high_weight_qids.append(q.id)
        if q.id not in done_qids:
            new_qids.append(q.id)

    if not valid_qids:
        if exclude:
            return pick_next_question(session, chapter_filter, set(), set())
        return None

    pools = [
        (due_qids, 0.50),
        (high_weight_qids, 0.25),
        (new_qids, 0.15),
        (valid_qids, 0.10),
    ]
    pools = [(p, w) for p, w in pools if p]
    if not pools:
        return None

    total_w = sum(w for _, w in pools)
    pools = [(p, w / total_w) for p, w in pools]

    # 7) 选池
    r = random.random()
    acc = 0.0
    chosen = pools[-1][0]
    for p, w in pools:
        acc += w
        if r <= acc:
            chosen = p
            break

    # 8) 池内加权（全内存）
    weights = []
    for qid in chosen:
        q = q_map[qid]
        chap_w = get_chap_w(q.chapter_name)
        kp_w = kp_importance_map.get(qid, 3)
        weights.append(max(0.0001, chap_w * kp_w))

    qid = random.choices(chosen, weights=weights, k=1)[0]
    return q_map[qid]


def pick_questions_batch(session, n, chapter_filter, year_filter=None, type_filter=None):
    """一次性抽 n 道题（加权、不重复）。开始本轮时调用一次，之后从内存取题，避免每次点击查库。"""
    now = datetime.now()

    # ============ 套卷模式（按年份 + 题号顺序） ============
    if year_filter and chapter_filter != "错题本":
        qq = session.query(Question).filter(_active_filter(), Question.year == year_filter)
        if chapter_filter != "全部章节":
            qq = qq.filter(Question.chapter_name == chapter_filter)
        if type_filter:
            qq = qq.filter(Question.question_type == type_filter)
        return qq.order_by(Question.question_no, Question.id).limit(n).all()

    # ============ 错题本模式 ============
    if chapter_filter == "错题本":
        wrong_qids = list(set(
            r[0] for r in
            session.query(StudyEvent.item_id)
            .filter(StudyEvent.item_type == "question", StudyEvent.is_correct == False)
            .distinct().all()
        ))
        if year_filter:
            year_qids = set(r[0] for r in session.query(Question.id).filter(Question.year == year_filter).all())
            wrong_qids = [qid for qid in wrong_qids if qid in year_qids]
        if type_filter:
            type_qids = set(r[0] for r in session.query(Question.id).filter(Question.question_type == type_filter).all())
            wrong_qids = [qid for qid in wrong_qids if qid in type_qids]
        if not wrong_qids:
            return []
        due_ris = (session.query(ReviewItem)
                   .filter(ReviewItem.item_type == "question",
                           ReviewItem.item_id.in_(wrong_qids),
                           ReviewItem.state != "archived")
                   .order_by(ReviewItem.due).limit(n).all())
        due_ids = [r.item_id for r in due_ris]
        remaining = [qid for qid in wrong_qids if qid not in due_ids]
        random.shuffle(remaining)
        chosen_ids = (due_ids + remaining)[:n]
        q_map = {q.id: q for q in session.query(Question).filter(Question.id.in_(chosen_ids), _active_filter()).all()}
        return [q_map[qid] for qid in chosen_ids if qid in q_map]

    # ============ 普通模式（加权抽 n 道） ============
    done_qids = set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question")
        .distinct().all()
    )
    all_q = session.query(Question).filter(_active_filter())
    if chapter_filter != "全部章节":
        all_q = all_q.filter(Question.chapter_name == chapter_filter)
    if type_filter:
        all_q = all_q.filter(Question.question_type == type_filter)
    all_candidates = all_q.all()
    if not all_candidates:
        return []

    qid_list = [q.id for q in all_candidates]
    q_map = {q.id: q for q in all_candidates}

    kp_importance_map = {}
    if qid_list:
        rows = (session.query(QuestionKP.question_id, KnowledgePoint.importance)
                .join(KnowledgePoint, KnowledgePoint.id == QuestionKP.kp_id)
                .filter(QuestionKP.question_id.in_(qid_list))
                .all())
        for qid, imp in rows:
            kp_importance_map[qid] = max(kp_importance_map.get(qid, 0), imp or 3)

    due_qid_set = set()
    due_rows = (session.query(ReviewItem.item_id)
                .filter(ReviewItem.item_type == "question",
                        ReviewItem.due <= now,
                        ReviewItem.state != "archived")
                .all())
    for (qid,) in due_rows:
        due_qid_set.add(qid)

    chapter_imp_cache = {}

    def get_chap_w(chap_name):
        if chap_name not in chapter_imp_cache:
            chapter_imp_cache[chap_name] = (
                get_chapter_importance(chap_name) if chap_name else 3
            )
        return chapter_imp_cache[chap_name]

    due_qids = []
    high_weight_qids = []
    new_qids = []
    valid_qids = []
    for q in all_candidates:
        valid_qids.append(q.id)
        if q.id in due_qid_set:
            due_qids.append(q.id)
        if kp_importance_map.get(q.id, 3) >= 4:
            high_weight_qids.append(q.id)
        if q.id not in done_qids:
            new_qids.append(q.id)

    chosen_ids = []
    for _ in range(min(n, len(valid_qids))):
        pools = [(p, w) for p, w in [
            (due_qids, 0.50), (high_weight_qids, 0.25),
            (new_qids, 0.15), (valid_qids, 0.10),
        ] if p]
        if not pools:
            break
        total_w = sum(w for _, w in pools)
        r = random.random() * total_w
        acc = 0.0
        chosen = pools[-1][0]
        for p, w in pools:
            acc += w
            if r <= acc:
                chosen = p
                break
        weights = [
            max(0.0001, get_chap_w(q_map[qid].chapter_name) * kp_importance_map.get(qid, 3))
            for qid in chosen
        ]
        qid = random.choices(chosen, weights=weights, k=1)[0]
        chosen_ids.append(qid)
        for p in (due_qids, high_weight_qids, new_qids, valid_qids):
            if qid in p:
                p.remove(qid)

    return [q_map[qid] for qid in chosen_ids]


def find_similar_question(session, source_qid, exclude_ids, chapter_fallback=False,
                          chapter_name=None):
    """基于知识点找相似题；fallback 时同章节随机"""
    kp_ids = [r[0] for r in
              session.query(QuestionKP.kp_id)
              .filter(QuestionKP.question_id == source_qid).all()]
    exclude = set(exclude_ids) | {source_qid}
    active = _active_filter()

    if kp_ids:
        q = (session.query(Question)
             .join(QuestionKP, QuestionKP.question_id == Question.id)
             .filter(QuestionKP.kp_id.in_(kp_ids))
             .filter(~Question.id.in_(exclude))
             .filter(active)
             .order_by(func.random())
             .first())
        if q:
            return q

    if chapter_fallback and chapter_name:
        return (session.query(Question)
                .filter(Question.chapter_name == chapter_name)
                .filter(~Question.id.in_(exclude))
                .filter(active)
                .order_by(func.random())
                .first())
    return None