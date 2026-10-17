# -*- coding: utf-8 -*-
"""把细胞题库（cell_tagged.json）导入数据库（subject='细胞'），并建知识点关联。"""
import os
import sys
import io
import json
import re
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, KnowledgePoint, QuestionKP

TYPE_MAP = {"名词解释": "名词解释", "简答": "问答", "论述": "问答"}


def main():
    data = json.load(open("data/output/细胞/cell_tagged.json", encoding="utf-8"))
    session = get_session()

    # 清空旧的细胞题
    old_ids = [r[0] for r in session.query(Question.id).filter(Question.subject == "细胞").all()]
    if old_ids:
        session.query(QuestionKP).filter(QuestionKP.question_id.in_(old_ids)).delete(synchronize_session=False)
    session.query(Question).filter(Question.subject == "细胞").delete(synchronize_session=False)
    session.query(KnowledgePoint).filter(KnowledgePoint.subject == "细胞").delete(synchronize_session=False)
    session.commit()

    # 导入题目
    year_counter = defaultdict(int)
    for d in data:
        year_counter[d["year"]] += 1
        session.add(Question(
            question_type=TYPE_MAP.get(d["type"], "问答"),
            stem=d["stem"],
            answer=d.get("answer"),
            year=d["year"],
            question_no=year_counter[d["year"]],
            kp_text=d.get("kp"),
            chapter_name=d.get("chapter"),
            answer_mode="self",
            data_status="正常",
            subject="细胞",
            kp_location=d.get("kp_location"),
            kp_key_point=d.get("kp_key_point"),
            kp_exam_point=d.get("kp_exam_point"),
            kp_frequency=d.get("kp_frequency"),
        ))
    session.commit()

    # 建知识点关联（subject='细胞'）
    qid_kps = {}
    kp_counter = Counter()
    for q in session.query(Question).filter(Question.subject == "细胞").all():
        kp = (q.kp_text or "").strip()
        if not kp:
            kp = (q.chapter_name or "").replace("第", "").replace("章", "").strip()
        parts = [p.strip() for p in re.split(r"[、，；;/,]", kp) if len(p.strip()) >= 2]
        qid_kps[q.id] = parts
        for p in parts:
            kp_counter[p] += 1

    kp_id_map = {}
    for name, cnt in kp_counter.items():
        importance = 5 if cnt >= 10 else (4 if cnt >= 5 else 3)
        kp = KnowledgePoint(name=name, importance=importance, subject="细胞")
        session.add(kp)
        session.flush()
        kp_id_map[name] = kp.id

    for qid, names in qid_kps.items():
        for name in names:
            if name in kp_id_map:
                session.add(QuestionKP(question_id=qid, kp_id=kp_id_map[name]))
    session.commit()

    n_q = session.query(Question).filter(Question.subject == "细胞").count()
    n_kp = session.query(KnowledgePoint).filter(KnowledgePoint.subject == "细胞").count()
    n_qkp = session.query(QuestionKP).count()
    print(f"✅ 细胞题 {n_q} 道，细胞知识点 {n_kp} 个，关联 {n_qkp} 条")
    print(f"生化题 {session.query(Question).filter(Question.subject=='生化').count()} 道（不受影响）")


if __name__ == "__main__":
    main()
