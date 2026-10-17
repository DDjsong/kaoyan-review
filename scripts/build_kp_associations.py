# -*- coding: utf-8 -*-
"""从题目的 kp_text 提取知识点，重建 knowledge_point 表和 question_kp 关联。

- 知识点按出现频次设置 importance（>=10 次→5，>=5 次→4，否则→3）
- 高权重知识点（importance>=4）会被抽题算法优先抽取
"""
import os
import sys
import io
import re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, KnowledgePoint, QuestionKP


def main():
    session = get_session()
    rows = session.query(Question.id, Question.kp_text, Question.chapter_name).all()

    qid_kps = {}
    kp_counter = Counter()
    for qid, kp_text, ch in rows:
        kp = (kp_text or "").strip()
        if not kp:
            # 兜底：用章节名做知识点
            kp = (ch or "").replace("第", "").replace("章", "").strip()
        parts = [p.strip() for p in re.split(r"[、，；;/,]", kp) if len(p.strip()) >= 2]
        qid_kps[qid] = parts
        for p in parts:
            kp_counter[p] += 1

    # 清空旧数据（旧 119 条是孤儿，重建）
    session.query(QuestionKP).delete()
    session.query(KnowledgePoint).delete()
    session.commit()

    kp_id_map = {}
    for name, cnt in kp_counter.items():
        importance = 5 if cnt >= 10 else (4 if cnt >= 5 else 3)
        kp = KnowledgePoint(name=name, importance=importance)
        session.add(kp)
        session.flush()
        kp_id_map[name] = kp.id

    added = 0
    for qid, names in qid_kps.items():
        for name in names:
            if name in kp_id_map:
                session.add(QuestionKP(question_id=qid, kp_id=kp_id_map[name]))
                added += 1

    session.commit()

    n_kp = session.query(KnowledgePoint).count()
    n_qkp = session.query(QuestionKP).count()
    n_q_with_kp = session.query(QuestionKP.question_id).distinct().count()
    print(f"知识点总数: {n_kp}")
    print(f"question_kp 关联数: {n_qkp}")
    print(f"有关联的题目数: {n_q_with_kp} / {session.query(Question).count()}")

    # 高频知识点 TOP 20
    print("\n高频知识点 TOP 20:")
    for name, cnt in kp_counter.most_common(20):
        print(f"  {name}: {cnt} 次 (importance={kp_id_map[name] and 5 if cnt>=10 else 4 if cnt>=5 else 3})")


if __name__ == "__main__":
    main()
