# -*- coding: utf-8 -*-
"""细胞题库去重：题干高度相似(>=0.85)的重复题只留一个（保留最早年份）。"""
import os
import sys
import io
import json
import re
from difflib import SequenceMatcher

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "data/output/细胞"


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[（(].*?[)）]", "", s)  # 去括号内容（如英文翻译）
    s = re.sub(r"[\s，。、；：,.!?？【】\[\]（）()]+", "", s)
    return s


def sim(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def main():
    data = json.load(open(os.path.join(BASE, "cell_merged.json"), encoding="utf-8"))
    data.sort(key=lambda x: (x["year"], x["type"]))  # 年份早的在前

    deduped = []
    removed = 0
    for q in data:
        is_dup = False
        for kept in deduped:
            if sim(q["stem"], kept["stem"]) >= 0.85:
                is_dup = True
                break
        if not is_dup:
            deduped.append(q)
        else:
            removed += 1

    out = os.path.join(BASE, "cell_deduped.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    # 统计
    from collections import Counter
    type_cnt = Counter(q["type"] for q in deduped)
    year_cnt = Counter(q["year"] for q in deduped)
    no_ans = sum(1 for q in deduped if not q["answer"])
    print(f"去重前 {len(data)} 道，去重后 {len(deduped)} 道（去除 {removed} 道重复）")
    print(f"题型分布: {dict(type_cnt)}")
    print(f"无答案: {no_ans} 道")
    print(f"年份分布: {dict(sorted(year_cnt.items()))}")


if __name__ == "__main__":
    main()
