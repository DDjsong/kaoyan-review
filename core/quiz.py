import random
from datetime import datetime
from sqlalchemy import func

from core.models import Question, ReviewItem, StudyEvent, KnowledgePoint, QuestionKP
from core.settings import get_chapter_importance


def _max_kp_importance(session, qid):
    kps = (session.query(KnowledgePoint)
           .join(QuestionKP, QuestionKP.kp_id == KnowledgePoint.id)
           .filter(QuestionKP.question_id == qid).all())
    if not kps:
        return 3
    return max(kp.importance for kp in kps)


def _question_weight(session, q):
    chap_w = get_chapter_importance(q.chapter_name) if q.chapter_name else 3
    kp_w = _max_kp_importance(session, q.id)
    return chap_w * kp_w


def _get_wrong_qids(session):
    """所有做错过的题目 id（list）"""
    return list(set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question",
                StudyEvent.is_correct == False)
        .distinct().all()
    ))


def pick_next_question(session, chapter_filter, exclude_ids, skip_ids):
    """按四池加权抽题。
    chapter_filter 可以是 '错题本' / '全部章节' / 具体章节名
    """
    now = datetime.now()
    exclude = set(exclude_ids) | set(skip_ids)

    # ============ 错题本模式（简化直接版） ============
    if chapter_filter == "错题本":
        wrong_qids = _get_wrong_qids(session)
        if not wrong_qids:
            return None

        # 候选：排除本轮已做、已跳过的
        candidates = [qid for qid in wrong_qids if qid not in exclude]
        if not candidates:
            # 全做过了，允许重复
            candidates = wrong_qids

        # 优先取到期的
        due_ris = (session.query(ReviewItem)
                   .filter(ReviewItem.item_type == "question",
                           ReviewItem.item_id.in_(candidates),
                           ReviewItem.due <= now,
                           ReviewItem.state != "archived")
                   .order_by(ReviewItem.due).all())

        if due_ris:
            chosen_id = due_ris[0].item_id
        else:
            chosen_id = random.choice(candidates)

        return session.query(Question).filter(Question.id == chosen_id).first()

    # ============ 普通模式 ============
    done_qids = set(
        r[0] for r in
        session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question")
        .distinct().all()
    )

    def base_q():
        q = session.query(Question)
        if chapter_filter != "全部章节":
            q = q.filter(Question.chapter_name == chapter_filter)
        return q

    def base_rq():
        q = session.query(ReviewItem).filter(
            ReviewItem.item_type == "question",
            ReviewItem.due <= now,
            ReviewItem.state != "archived",
        )
        if chapter_filter != "全部章节":
            q = q.join(Question, Question.id == ReviewItem.item_id).filter(
                Question.chapter_name == chapter_filter)
        return q

    rq = base_rq()
    if exclude:
        rq = rq.filter(~ReviewItem.item_id.in_(exclude))
    due_qids = [ri.item_id for ri in rq.all()]

    all_q = base_q()
    if exclude:
        all_q = all_q.filter(~Question.id.in_(exclude))
    all_candidates = all_q.all()
    if not all_candidates:
        if exclude:
            return pick_next_question(session, chapter_filter, set(), set())
        return None

    all_qids = [q.id for q in all_candidates]

    high_weight_qids = []
    for q in all_candidates:
        if _max_kp_importance(session, q.id) >= 4:
            high_weight_qids.append(q.id)

    new_qids = [qid for qid in all_qids if qid not in done_qids]

    pools = [
        (due_qids, 0.50),
        (high_weight_qids, 0.25),
        (new_qids, 0.15),
        (all_qids, 0.10),
    ]
    pools = [(p, w) for p, w in pools if p]
    if not pools:
        return None

    total_w = sum(w for _, w in pools)
    pools = [(p, w / total_w) for p, w in pools]

    r = random.random()
    acc = 0.0
    chosen = pools[-1][0]
    for p, w in pools:
        acc += w
        if r <= acc:
            chosen = p
            break

    weights = []
    for qid in chosen:
        q = session.query(Question).filter(Question.id == qid).first()
        if q is None:
            weights.append(0.0001)
        else:
            weights.append(max(0.0001, _question_weight(session, q)))

    qid = random.choices(chosen, weights=weights, k=1)[0]
    return session.query(Question).filter(Question.id == qid).first()


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