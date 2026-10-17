# -*- coding: utf-8 -*-
"""把 cell_deduped.json 生成细胞题库 Excel（结构对齐生化总题库）。"""
import os
import sys
import io
import json
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

BASE = "data/output/细胞"
OUT = "data/exams/细胞/细胞总题库.xlsx"

# 题型映射：简答/论述 -> 问答（与生化题库的 question_type 对齐）
TYPE_MAP = {"名词解释": "名词解释", "简答": "问答", "论述": "问答"}


def main():
    data = json.load(open(os.path.join(BASE, "cell_deduped.json"), encoding="utf-8"))

    # 每年每个题型内编号
    counter = defaultdict(int)
    rows = []
    for q in data:
        counter[q["year"]] += 1
        qtype = TYPE_MAP.get(q["type"], q["type"])
        rows.append({
            "年份": q["year"],
            "题型": qtype,
            "题号": counter[q["year"]],
            "题干": q["stem"],
            "选项A": None,
            "选项B": None,
            "选项C": None,
            "选项D": None,
            "答案": q["answer"],
            "解析": None,
            "考点": None,
            "章节": None,
            "answer_mode": "self",
            "user_answer": None,
            "题目状态": "正常",
        })

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_excel(OUT, index=False)
    print(f"✅ 生成 {len(df)} 道细胞题 -> {OUT}")
    print(f"题型分布: {df['题型'].value_counts().to_dict()}")
    print(f"年份分布: {df['年份'].value_counts().sort_index().to_dict()}")


if __name__ == "__main__":
    main()
