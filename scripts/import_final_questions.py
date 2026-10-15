"""
把「生化总题库.xlsx」导入数据库（本地 SQLite 或云端 Supabase）。

用法（在 PyCharm Terminal 里）:
    python scripts/import_final_questions.py

重要说明:
1. 目标库由 core/db.py 决定：
   - 配了 Streamlit Secrets 的 [supabase] 或环境变量 SUPABASE_* → 写云端 Supabase
   - 都没有 → 写本地 SQLite (data/kaoyan.db)
   脚本会打印实际写入的库，跑之前务必确认。
2. 会清空 question / question_kp / review_item / study_event / ai_advice。
   因为重新导入后题目 id 会重排，旧的学习记录会指向错误的题，必须一起重置。
3. 「题目状态 = 停用」的题不会导入（例如 2026 年暂无答案的题）。
4. 跑之前请先执行 ALTER TABLE 给 question 表加上
   question_no / answer_mode / data_status 三个字段（见报告里的 SQL）。
"""
import os
import sys
import io
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import inspect

from core.db import engine, get_session, DB_PATH
from core.models import (
    Base, Question, QuestionKP, ReviewItem, StudyEvent, AIAdvice
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL = os.path.join(BASE_DIR, "data", "exams", "生化", "生化总题库.xlsx")


def is_blank(v):
    return pd.isna(v) or str(v).strip() in ("", "nan", "None")


def main():
    if not os.path.exists(EXCEL):
        print(f"[X] 找不到题库文件: {EXCEL}")
        sys.exit(1)

    print(f"[读] 题库文件: {EXCEL}")
    df = pd.read_excel(EXCEL)
    print(f"     共 {len(df)} 行")

    # 确保表存在（已存在的表不会被 create_all 改动）
    Base.metadata.create_all(engine)
    print(f"[库] 目标数据库: {DB_PATH}")

    # 先检查字段是否齐全
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("question")]
    missing = [c for c in ("question_no", "answer_mode", "data_status") if c not in cols]
    if missing:
        print(f"\n[X] question 表缺少字段 {missing}")
        print("    请先在数据库里执行:")
        print("    ALTER TABLE question ADD COLUMN question_no INTEGER;")
        print("    ALTER TABLE question ADD COLUMN answer_mode VARCHAR(20);")
        print("    ALTER TABLE question ADD COLUMN data_status VARCHAR(20) DEFAULT '正常';")
        sys.exit(1)

    session = get_session()

    # ---- 重置旧数据 ----
    print("[清] 清空旧数据（题目 / 题目-知识点 / 复习项 / 学习记录 / AI 建议）...")
    session.query(QuestionKP).delete()
    session.query(ReviewItem).delete()
    session.query(StudyEvent).delete()
    session.query(AIAdvice).delete()
    session.query(Question).delete()
    session.commit()

    added, skipped = 0, 0
    for _, r in df.iterrows():
        status = str(r.get("题目状态", "正常")).strip()
        if status in ("", "nan", "None"):
            status = "正常"
        if status == "停用":
            skipped += 1
            continue

        opts = {}
        for k, col in [("A", "选项A"), ("B", "选项B"), ("C", "选项C"), ("D", "选项D")]:
            v = r.get(col)
            if not is_blank(v):
                opts[k] = str(v).strip()

        am = r.get("answer_mode")
        session.add(Question(
            question_type=str(r["题型"]).strip() if not is_blank(r["题型"]) else None,
            stem=str(r["题干"]).strip() if not is_blank(r["题干"]) else "",
            options=json.dumps(opts, ensure_ascii=False) if opts else None,
            answer=str(r["答案"]).strip() if not is_blank(r["答案"]) else None,
            explanation=str(r["解析"]).strip() if not is_blank(r["解析"]) else None,
            year=int(r["年份"]) if not is_blank(r["年份"]) else None,
            kp_text=str(r["考点"]).strip() if not is_blank(r["考点"]) else None,
            chapter_name=str(r["章节"]).strip() if not is_blank(r["章节"]) else None,
            question_no=int(r["题号"]) if not is_blank(r["题号"]) else None,
            answer_mode=str(am).strip() if not is_blank(am) else None,
            data_status=status,
        ))
        added += 1

    session.commit()

    total = session.query(Question).count()
    n_doubt = session.query(Question).filter(Question.data_status == "存疑").count()
    print(f"\n[√] 导入完成: 新增 {added} 道, 跳过「停用」{skipped} 道")
    print(f"    库中题目总数: {total}（其中「存疑」{n_doubt} 道）")


if __name__ == "__main__":
    main()
