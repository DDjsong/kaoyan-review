# -*- coding: utf-8 -*-
"""整合细胞生物学题目+答案：2007-2015 用「题目JSON题干 + 答案JSON原文答案」匹配，
2016-2025 直接用南开821（题目+答案都全）。输出统一的 cell_merged.json。"""
import os
import sys
import io
import json
from difflib import SequenceMatcher

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "data/output/细胞"


def sim(a, b):
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def main():
    nankai = json.load(open(os.path.join(BASE, "nankai821_qa.json"), encoding="utf-8"))
    answers = json.load(open(os.path.join(BASE, "cell_answer_2007_2015.json"), encoding="utf-8"))
    questions = json.load(open(os.path.join(BASE, "cell1_questions_2007_2015.json"), encoding="utf-8"))

    merged = []  # 2016-2025
    for q in nankai:
        merged.append({"year": q["year"], "type": q["type"], "stem": q["stem"], "answer": q.get("answer")})

    # 2007-2015 匹配
    ans_by_year = {}
    for a in answers:
        ans_by_year.setdefault(a["year"], []).append(a)

    matched = []
    unmatched = []
    for q in questions:
        year = q["year"]
        cands = ans_by_year.get(year, [])
        best = None
        best_sim = 0.0
        for a in cands:
            s = sim(q["stem"], a["stem"])
            if s > best_sim:
                best_sim = s
                best = a
        if best and best_sim >= 0.55:
            matched.append({
                "year": year, "type": q["type"], "stem": q["stem"],
                "answer": best["answer"], "sim": round(best_sim, 2),
            })
        else:
            unmatched.append({"year": year, "type": q["type"], "stem": q["stem"], "sim": round(best_sim, 2)})

    print(f"南开821(2016-2025): {len(merged)} 道")
    print(f"2007-2015 匹配成功: {len(matched)} 道")
    print(f"2007-2015 未匹配: {len(unmatched)} 道")
    if unmatched:
        print("\n未匹配的题目:")
        for u in unmatched:
            print(f"  [{u['year']}] {u['type']} sim={u['sim']} {u['stem'][:50]}")

    all_qa = merged + matched
    # 按年份、题型排序
    all_qa.sort(key=lambda x: (x["year"], x["type"]))
    out = os.path.join(BASE, "cell_merged.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_qa, f, ensure_ascii=False, indent=2)
    print(f"\n合并后共 {len(all_qa)} 道，输出: {out}")


if __name__ == "__main__":
    main()
