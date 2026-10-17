# -*- coding: utf-8 -*-
"""用 DeepSeek 批量给题库打「章节 + 考点」标签（可断点续传）。

用法:  python scripts/tag_questions.py [每批题数, 默认30]
只处理 chapter_name 为空的题，打完后写回数据库的 chapter_name 和 kp_text。
"""
import os
import sys
import io
import json
import time
import tomllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from core.db import get_session
from core.models import Question

# 完整章节体系（《现代生物化学》黄熙泰 第三版，20 章）
CHAPTERS = [
    "第1章 绪论",
    "第2章 蛋白质化学",
    "第3章 酶学",
    "第4章 核苷酸和核酸",
    "第5章 碳水化合物和糖生物学",
    "第6章 维生素与辅酶",
    "第7章 生物膜",
    "第8章 激素与生物信号转导",
    "第9章 新陈代谢引论",
    "第10章 糖代谢",
    "第11章 生物氧化",
    "第12章 光合作用",
    "第13章 脂代谢",
    "第14章 氨基酸代谢",
    "第15章 核苷酸代谢",
    "第16章 DNA的复制、修复和重组",
    "第17章 RNA代谢",
    "第18章 蛋白质的生物合成与修饰",
    "第19章 基因表达的调节",
    "第20章 重组DNA技术与基因组学",
]


def get_key():
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            data = tomllib.load(f)
        k = data.get("DEEPSEEK_API_KEY")
        if k:
            return k
    except Exception:
        pass
    return os.environ.get("DEEPSEEK_API_KEY")


def build_prompt(items_text):
    chapters = "\n".join(CHAPTERS)
    return (
        "你是生物化学考研辅导专家。请给下面的考研真题分类。\n\n"
        "章节列表（每题必须从以下章节中选最合适的一个，不要自创章节）：\n"
        f"{chapters}\n\n"
        "对每道题输出两个字段：\n"
        "- chapter：章节名（严格从上面列表选）\n"
        "- kp：1-3 个知识点关键词，用「、」分隔（如「DNA聚合酶、错配修复」）\n\n"
        "题目：\n"
        f"{items_text}\n\n"
        '只返回 JSON，不要任何多余文字，格式如下：\n'
        '{"questions": [{"idx": 1, "chapter": "第2章 蛋白质化学", "kp": "氨基酸、滴定"}, ...]}'
    )


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)


def main():
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    api_key = get_key()
    if not api_key:
        print("❌ 未找到 DEEPSEEK_API_KEY")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    session = get_session()

    from sqlalchemy import or_
    qs = (session.query(Question)
          .filter(or_(Question.chapter_name.is_(None), Question.chapter_name == ""))
          .order_by(Question.year, Question.question_no, Question.id)
          .all())
    print(f"待打标签: {len(qs)} 道，每批 {batch_size} 道")

    done = 0
    fail = 0
    for start in range(0, len(qs), batch_size):
        batch = qs[start:start + batch_size]
        items = []
        for i, q in enumerate(batch, 1):
            stem = (q.stem or "").replace("\n", " ")[:120]
            items.append(f"{i}. [{q.year}年 {q.question_type or ''}] {stem}")
        prompt = build_prompt("\n".join(items))

        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=4000,
                )
                content = resp.choices[0].message.content
                data = extract_json(content)
                qs_json = data.get("questions", [])
                for item in qs_json:
                    idx = int(item.get("idx", 0))
                    if 1 <= idx <= len(batch):
                        q = batch[idx - 1]
                        q.chapter_name = str(item.get("chapter", "")).strip()
                        q.kp_text = str(item.get("kp", "")).strip()
                session.commit()
                done += len(batch)
                print(f"  ✅ 已完成 {done}/{len(qs)} (批 {start // batch_size + 1})")
                break
            except Exception as e:
                if attempt == 2:
                    fail += len(batch)
                    print(f"  ❌ 批 {start // batch_size + 1} 失败: {e}")
                else:
                    time.sleep(3)
        time.sleep(1)

    # 汇总
    n_ch = (session.query(Question)
            .filter(Question.chapter_name.isnot(None), Question.chapter_name != "").count())
    n_kp = (session.query(Question)
            .filter(Question.kp_text.isnot(None), Question.kp_text != "").count())
    total = session.query(Question).count()
    print(f"\n完成。章节非空 {n_ch}/{total}，考点非空 {n_kp}/{total}，失败 {fail} 道")


if __name__ == "__main__":
    main()
