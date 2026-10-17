# -*- coding: utf-8 -*-
"""用 DeepSeek 从细胞生物学真题 txt 提取「题目 + 答案」（只留名词解释/简答/论述）。

用法: python scripts/parse_cell_qa.py <txt路径> <输出json路径> [起始年份] [结束年份]
"""
import os
import sys
import io
import json
import re
import time
import tomllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI


def get_key():
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f)["DEEPSEEK_API_KEY"]
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY")


def split_by_year(text, start_year=None, end_year=None):
    """按年份标记切分文本。返回 [(year, block), ...]"""
    # 年份标记（仅匹配行首，避免答案里的「（与细胞21年7.同）」等引用被误切）
    parts = re.split(r"(?=^细胞\s*\d{2}\s*年|^\d{4}\s*年)", text, flags=re.MULTILINE)
    result = []
    for p in parts:
        m = re.search(r"(?:细胞\s*(\d{2})\s*年|(\d{4})\s*年)", p)
        if not m:
            continue
        if m.group(1):
            year = 2000 + int(m.group(1))
        else:
            year = int(m.group(2))
        if start_year and year < start_year:
            continue
        if end_year and year > end_year:
            continue
        result.append((year, p.strip()))
    return result


def parse_block(client, year, block):
    prompt = (
        "你是考研资料整理助手。下面是一段细胞生物学考研真题（题目+答案）。\n\n"
        "请提取其中的【名词解释、简答题/问答题、论述题】的题目和答案。\n"
        "**忽略**选择题、判断题、填空题等客观题。\n\n"
        "对每道题输出：\n"
        "- type: 题型，只能是「名词解释」「简答」「论述」之一\n"
        "- stem: 题干（完整，去掉题号）\n"
        "- answer: 答案（完整）\n\n"
        "只返回 JSON：{\"questions\": [{\"type\": \"...\", \"stem\": \"...\", \"answer\": \"...\"}]}\n"
        f"年份：{year} 年\n\n"
        f"内容：\n{block}"
    )
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=8000,
            )
            content = resp.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.rstrip().endswith("```"):
                    content = content.rstrip()[:-3]
            return json.loads(content)
        except Exception as e:
            if attempt == 2:
                print(f"  [X] {year} 年解析失败: {e}")
                return {"questions": []}
            time.sleep(3)


def main():
    txt_path = sys.argv[1]
    out_path = sys.argv[2]
    start_year = int(sys.argv[3]) if len(sys.argv) > 3 else None
    end_year = int(sys.argv[4]) if len(sys.argv) > 4 else None

    api_key = get_key()
    if not api_key:
        print("❌ 未找到 DEEPSEEK_API_KEY")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    text = open(txt_path, encoding="utf-8").read()
    blocks = split_by_year(text, start_year, end_year)
    print(f"共 {len(blocks)} 个年份块")

    all_questions = []
    for year, block in blocks:
        print(f"解析 {year} 年 ({len(block)} 字符)...")
        data = parse_block(client, year, block)
        qs = data.get("questions", [])
        for q in qs:
            q["year"] = year
        all_questions.extend(qs)
        print(f"  -> {len(qs)} 道")
        time.sleep(1)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 共提取 {len(all_questions)} 道，输出: {out_path}")


if __name__ == "__main__":
    main()
