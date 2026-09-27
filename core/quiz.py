import random
from datetime import datetime
from sqlalchemy import func
import streamlit as st
from core.models import Question, ReviewItem, StudyEvent, KnowledgePoint, QuestionKP
from core.settings import get_chapter_importance


def pick_next_question(session, chapter_filter, exclude_ids, skip_ids):
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

        return session.query(Question).filter(Question.id == chosen_id).first()

    # ============ 普通模式 ============
    # 1) 一次查询：所有做过的题
    done_qids = set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question")
        .distinct().all()
    )

    # 2) 一次查询：候选题目（全部）
    all_q = session.query(Question)
    if chapter_filter != "全部章节":
        all_q = all_q.filter(Question.chapter_name == chapter_filter)
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
        # 全部被排除，重试一次（清空 exclude）
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


def find_similar_question(session, source_qid, exclude_ids, chapter_fallback=False,
                          chapter_name=None):
    """基于知识点找相似题；fallback 时同章节随机"""
    kp_ids = [r[0] for r in
              session.query(QuestionKP.kp_id)
              .filter(QuestionKP.question_id == source_qid).all()]
    exclude = set(exclude_ids) | {source_qid}

    if kp_ids:
        q = (session.query(Question)
             .join(QuestionKP, QuestionKP.question_id == Question.id)
             .filter(QuestionKP.kp_id.in_(kp_ids))
             .filter(~Question.id.in_(exclude))
             .order_by(func.random())
             .first())
        if q:
            return q

    if chapter_fallback and chapter_name:
        return (session.query(Question)
                .filter(Question.chapter_name == chapter_name)
                .filter(~Question.id.in_(exclude))
                .order_by(func.random())
                .first())
    return None