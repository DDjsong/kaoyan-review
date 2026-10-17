# -*- coding: utf-8 -*-
"""用 DeepSeek 给生化题补「知识点定位/重点/考点/考频」（章节和考点已有）。
可断点续传：只处理 kp_location 为空的题。"""
import os
import sys
import io
import json
import time
import tomllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from sqlalchemy import or_
from core.db import get_session
from core.models import Question


def get_key():
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f)["DEEPSEEK_API_KEY"]
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY")


def build_prompt(items):
    return (
        "你是生物化学考研辅导专家。下面每道题已给出「章节」和「考点」，请补充其余字段。\n\n"
        "对每道题输出：\n"
        "- kp_location：该知识点在教材的精确定位，格式「第X章 XXX · 第X节 XXX · 第X小节 XXX」\n"
        "- kp_key_point：该知识点的重点内容（40字内）\n"
        "- kp_exam_point：考试通常怎么考这个点（40字内）\n"
        "- kp_frequency：考频，只能是「高频」「中频」「低频」\n\n"
        "题目：\n" + items + "\n\n"
        '只返回 JSON：{"questions": [{"idx": 1, "kp_location": "...", '
        '"kp_key_point": "...", "kp_exam_point": "...", "kp_frequency": "高频"}, ...]}'
    )


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)


def main():
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    api_key = get_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    session = get_session()

    qs = (session.query(Question)
          .filter(Question.subject == "生化")
          .filter(or_(Question.kp_location.is_(None), Question.kp_location == ""))
          .order_by(Question.year, Question.question_no, Question.id)
          .all())
    print(f"待补知识点信息: {len(qs)} 道，每批 {batch}")

    done = 0
    for start in range(0, len(qs), batch):
        chunk = qs[start:start + batch]
        items = "\n".join(
            f"{i}. [章节:{c.chapter_name}] [考点:{c.kp_text or ''}] [题干]{(c.stem or '')[:80]}"
            for i, c in enumerate(chunk, 1)
        )
        prompt = build_prompt(items)
        ok = False
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2, max_tokens=6000,
                )
                data = extract_json(resp.choices[0].message.content)
                for item in data.get("questions", []):
                    idx = int(item.get("idx", 0))
                    if 1 <= idx <= len(chunk):
                        c = chunk[idx - 1]
                        c.kp_location = str(item.get("kp_location", "")).strip()
                        c.kp_key_point = str(item.get("kp_key_point", "")).strip()
                        c.kp_exam_point = str(item.get("kp_exam_point", "")).strip()
                        c.kp_frequency = str(item.get("kp_frequency", "")).strip()
                session.commit()
                done += len(chunk)
                print(f"  已完成 {done}/{len(qs)}")
                ok = True
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [X] 批 {start // batch + 1} 失败: {e}")
                time.sleep(3)
        time.sleep(1)

    n = (session.query(Question)
         .filter(Question.subject == "生化", Question.kp_location.isnot(None), Question.kp_location != "").count())
    print(f"\n✅ 完成，生化题有定位信息 {n} 道")


if __name__ == "__main__":
    main()
