# -*- coding: utf-8 -*-
"""用 DeepSeek 把 2007-2015 的题目和答案一一配对（答案文件的题干是简化版，规则匹配不可靠）。"""
import os
import sys
import io
import json
import time
import tomllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

BASE = "data/output/细胞"


def get_key():
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f)["DEEPSEEK_API_KEY"]
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY")


def main():
    api_key = get_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    answers = json.load(open(os.path.join(BASE, "cell_answer_2007_2015.json"), encoding="utf-8"))
    questions = json.load(open(os.path.join(BASE, "cell1_questions_2007_2015.json"), encoding="utf-8"))

    # 按年份分组
    from collections import defaultdict
    ans_by_year = defaultdict(list)
    for a in answers:
        ans_by_year[a["year"]].append(a)
    q_by_year = defaultdict(list)
    for q in questions:
        q_by_year[q["year"]].append(q)

    merged = []  # 2016-2025
    nankai = json.load(open(os.path.join(BASE, "nankai821_qa.json"), encoding="utf-8"))
    for q in nankai:
        merged.append({"year": q["year"], "type": q["type"], "stem": q["stem"], "answer": q.get("answer")})

    for year in sorted(q_by_year.keys()):
        qs = q_by_year[year]
        ans = ans_by_year.get(year, [])
        if not ans:
            for q in qs:
                merged.append({"year": year, "type": q["type"], "stem": q["stem"], "answer": None})
            continue

        # 构建 prompt
        q_text = "\n".join(f"题目{i+1}. [{q['type']}] {q['stem']}" for i, q in enumerate(qs))
        a_text = "\n".join(f"答案{i+1}. {a['stem']}" for i, a in enumerate(ans))
        prompt = (
            "下面同一年的细胞生物学真题的题目和答案，请一一配对（答案列表里的题干可能是题目简化版，按内容语义匹配）。\n\n"
            f"题目列表：\n{q_text}\n\n答案列表：\n{a_text}\n\n"
            '只返回 JSON，格式：{"pairs": [{"q": 题目编号, "a": 答案编号}, ...]}，没有对应答案的题目不要出现在 pairs 里。'
        )
        data = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4000,
                )
                content = resp.choices[0].message.content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    if content.rstrip().endswith("```"):
                        content = content.rstrip()[:-3]
                data = json.loads(content)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [X] {year} 年匹配失败: {e}")
                time.sleep(3)

        pairs = data.get("pairs", []) if data else []
        paired_q = set()
        for p in pairs:
            qi = int(p["q"]) - 1
            ai = int(p["a"]) - 1
            if 0 <= qi < len(qs) and 0 <= ai < len(ans):
                merged.append({
                    "year": year, "type": qs[qi]["type"],
                    "stem": qs[qi]["stem"], "answer": ans[ai]["answer"],
                })
                paired_q.add(qi)
        # 未配对的题目
        for qi, q in enumerate(qs):
            if qi not in paired_q:
                merged.append({"year": year, "type": q["type"], "stem": q["stem"], "answer": None})
        print(f"{year} 年：{len(qs)} 题，配对 {len(paired_q)}，无答案 {len(qs) - len(paired_q)}")
        time.sleep(1)

    merged.sort(key=lambda x: (x["year"], x["type"]))
    out = os.path.join(BASE, "cell_merged.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    n_no_ans = sum(1 for m in merged if not m["answer"])
    print(f"\n合并后共 {len(merged)} 道，其中无答案 {n_no_ans} 道，输出: {out}")


if __name__ == "__main__":
    main()
