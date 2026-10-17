# -*- coding: utf-8 -*-
"""把细胞题的章节/考点等标签写回细胞总题库 Excel。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from core.db import get_session
from core.models import Question

EXCEL = os.path.join("data", "exams", "细胞", "细胞总题库.xlsx")


def main():
    session = get_session()
    q_map = {}
    for q in session.query(Question).filter(Question.subject == "细胞").all():
        q_map[(q.year, (q.stem or "").strip())] = (q.chapter_name, q.kp_text)

    df = pd.read_excel(EXCEL)
    df["章节"] = df["章节"].astype("object")
    df["考点"] = df["考点"].astype("object")

    matched = 0
    for i, row in df.iterrows():
        year = row.get("年份")
        stem = row.get("题干")
        if pd.isna(stem):
            continue
        key = (year, str(stem).strip())
        if key in q_map:
            ch, kp = q_map[key]
            df.at[i, "章节"] = ch or ""
            df.at[i, "考点"] = kp or ""
            matched += 1

    df.to_excel(EXCEL, index=False)
    print(f"✅ 写回 {matched} / {len(df)} 道 -> {EXCEL}")


if __name__ == "__main__":
    main()
