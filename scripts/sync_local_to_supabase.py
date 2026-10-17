# -*- coding: utf-8 -*-
"""一键同步：把本地 SQLite 的完整题库（题目+知识点+关联）搬到云端 Supabase。

用法（先设置好 SUPABASE_* 环境变量）:
    python scripts/sync_local_to_supabase.py

说明：
1. 目标库由 core/db.py 决定：设置了 SUPABASE_* 环境变量 -> 写云端；否则报错退出。
2. 会清空云端 question / question_kp / knowledge_point / review_item / study_event / ai_advice，
   再从本地完整导入（含 subject、知识点定位/重点/考点/考频 等所有字段）。
3. 题目 id 会按插入顺序重排（1..N），知识点关联用映射后的新 id 重建。
"""
import os
import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import engine, get_session
from core.models import Question, KnowledgePoint, QuestionKP, ReviewItem, StudyEvent, AIAdvice

LOCAL_DB = os.path.join("data", "kaoyan.db")

QUESTION_FIELDS = [
    "type", "question_type", "stem", "options", "blanks", "answer", "explanation",
    "source", "year", "kp_text", "chapter_name", "chapter_id", "book",
    "question_no", "answer_mode", "data_status", "subject",
    "kp_location", "kp_key_point", "kp_exam_point", "kp_frequency",
]


def main():
    # 1. 确认目标库是云端
    url = str(engine.url)
    if not url.startswith("postgresql"):
        print("❌ 目标库不是云端 Supabase。请先在同一终端设置 SUPABASE_* 环境变量。")
        print(f"   当前目标库: {url}")
        sys.exit(1)
    print(f"目标库: 云端 Supabase")

    # 2. 读本地 SQLite
    if not os.path.exists(LOCAL_DB):
        print(f"❌ 找不到本地库: {LOCAL_DB}")
        sys.exit(1)
    local = sqlite3.connect(LOCAL_DB)
    local.row_factory = sqlite3.Row
    questions = [dict(r) for r in local.execute("SELECT * FROM question ORDER BY id").fetchall()]
    kps = [dict(r) for r in local.execute("SELECT * FROM knowledge_point ORDER BY id").fetchall()]
    qkps = [dict(r) for r in local.execute("SELECT * FROM question_kp").fetchall()]
    local.close()
    print(f"本地: {len(questions)} 题, {len(kps)} 知识点, {len(qkps)} 关联")

    # 3. 清空云端
    session = get_session()
    print("清空云端旧数据...")
    session.query(QuestionKP).delete()
    session.query(ReviewItem).delete()
    session.query(StudyEvent).delete()
    session.query(AIAdvice).delete()
    session.query(Question).delete()
    session.query(KnowledgePoint).delete()
    session.commit()

    # 4. 导入题目
    print("导入题目...")
    qid_map = {}
    for q in questions:
        obj = Question(**{f: q.get(f) for f in QUESTION_FIELDS})
        session.add(obj)
        session.flush()
        qid_map[q["id"]] = obj.id
    session.commit()

    # 5. 导入知识点
    print("导入知识点...")
    kpid_map = {}
    for kp in kps:
        obj = KnowledgePoint(
            name=kp.get("name"),
            chapter_id=kp.get("chapter_id"),
            parent_id=kp.get("parent_id"),
            importance=kp.get("importance", 3),
            summary=kp.get("summary"),
            source_ref=kp.get("source_ref"),
            subject=kp.get("subject"),
        )
        session.add(obj)
        session.flush()
        kpid_map[kp["id"]] = obj.id
    session.commit()

    # 6. 导入题目-知识点关联
    print("导入关联...")
    n_qkp = 0
    for qkp in qkps:
        qid = qid_map.get(qkp["question_id"])
        kpid = kpid_map.get(qkp["kp_id"])
        if qid is not None and kpid is not None:
            session.add(QuestionKP(question_id=qid, kp_id=kpid))
            n_qkp += 1
    session.commit()

    # 7. 验证
    n_q = session.query(Question).count()
    n_kp = session.query(KnowledgePoint).count()
    n_qkp2 = session.query(QuestionKP).count()
    print(f"\n✅ 同步完成：题目 {n_q}, 知识点 {n_kp}, 关联 {n_qkp2}")
    print("   请到 Supabase 或 Streamlit Cloud 验证。")


if __name__ == "__main__":
    main()
