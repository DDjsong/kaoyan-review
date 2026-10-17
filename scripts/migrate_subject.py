# -*- coding: utf-8 -*-
"""数据库迁移：给 question / knowledge_point 加 subject 和知识点信息字段，并给现有生化题标 subject='生化'。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from core.db import engine, get_session

# 要新增的列：表 -> [(列名, 类型)]
NEW_COLS = {
    "question": [
        ("subject", "VARCHAR(20)"),
        ("kp_location", "TEXT"),
        ("kp_key_point", "TEXT"),
        ("kp_exam_point", "TEXT"),
        ("kp_frequency", "VARCHAR(50)"),
    ],
    "knowledge_point": [
        ("subject", "VARCHAR(20)"),
    ],
}


def main():
    insp = inspect(engine)
    with engine.connect() as conn:
        for table, cols in NEW_COLS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ctype in cols:
                if name not in existing:
                    sql = f'ALTER TABLE {table} ADD COLUMN {name} {ctype}'
                    conn.execute(text(sql))
                    print(f"  [+] {table}.{name} ({ctype})")
                else:
                    print(f"  [~] {table}.{name} 已存在")
        conn.commit()

    # 给现有生化题标 subject
    session = get_session()
    from core.models import Question, KnowledgePoint
    n_q = session.query(Question).filter(
        (Question.subject.is_(None)) | (Question.subject == "")
    ).update({"subject": "生化"})
    n_kp = session.query(KnowledgePoint).filter(
        (KnowledgePoint.subject.is_(None)) | (KnowledgePoint.subject == "")
    ).update({"subject": "生化"})
    session.commit()
    print(f"\n标记生化题: {n_q} 道，生化知识点: {n_kp} 个")


if __name__ == "__main__":
    main()
