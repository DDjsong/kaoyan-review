# -*- coding: utf-8 -*-
"""用 DeepSeek 给细胞题库打标签：章节/考点/知识点定位/重点/考点/考频。
读取 data/output/细胞/cell_deduped.json，输出 cell_tagged.json。"""
import os
import sys
import io
import json
import time
import tomllib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI

CHAPTERS = [
    "第1章 绪论", "第2章 细胞生物学研究方法", "第3章 细胞质膜",
    "第4章 物质跨膜运输", "第5章 细胞质基质与内膜系统",
    "第6章 蛋白质分选与囊泡运输", "第7章 线粒体和叶绿体",
    "第8章 细胞骨架", "第9章 细胞核与染色质", "第10章 细胞信号转导",
    "第11章 细胞连接与细胞外基质", "第12章 细胞周期与细胞分裂",
    "第13章 细胞分化与干细胞", "第14章 细胞衰老与细胞死亡", "第15章 癌细胞",
]


def get_key():
    try:
        with open(".streamlit/secrets.toml", "rb") as f:
            return tomllib.load(f)["DEEPSEEK_API_KEY"]
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY")


def build_prompt(items):
    chapters = "\n".join(CHAPTERS)
    return (
        "你是细胞生物学考研辅导专家。请给下面的细胞生物学考研真题打标签。\n\n"
        "章节列表（每题从以下选最合适的一个，不要自创）：\n"
        f"{chapters}\n\n"
        "对每道题输出字段：\n"
        "- chapter：章节名（严格从上面选）\n"
        "- kp：1-3 个知识点关键词，用「、」分隔\n"
        "- kp_location：该知识点在教材的精确定位，格式「第X章 XXX · 第X节 XXX · 第X小节 XXX」\n"
        "- kp_key_point：该知识点的重点内容（40字内）\n"
        "- kp_exam_point：考试通常怎么考这个点（40字内）\n"
        "- kp_frequency：考频，只能是「高频」「中频」「低频」\n\n"
        "题目：\n" + items + "\n\n"
        '只返回 JSON：{"questions": [{"idx": 1, "chapter": "...", "kp": "...", '
        '"kp_location": "...", "kp_key_point": "...", "kp_exam_point": "...", "kp_frequency": "高频"}, ...]}'
    )


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)


def main():
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    api_key = get_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    data = json.load(open("data/output/细胞/cell_deduped.json", encoding="utf-8"))
    print(f"待打标签: {len(data)} 道")

    out_path = "data/output/细胞/cell_tagged.json"
    if os.path.exists(out_path):
        done_data = json.load(open(out_path, encoding="utf-8"))
        done_ids = set()
        for d in done_data:
            done_ids.add((d["year"], d["stem"]))
        remaining = [d for d in data if (d["year"], d["stem"]) not in done_ids]
        data = remaining
        print(f"已打 {len(done_data)} 道，剩 {len(remaining)} 道")
    else:
        done_data = []

    for start in range(0, len(data), batch):
        chunk = data[start:start + batch]
        items = "\n".join(
            f"{i}. [{c['year']}年 {c['type']}] {c['stem'][:100]}"
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
                data_json = extract_json(resp.choices[0].message.content)
                for item in data_json.get("questions", []):
                    idx = int(item.get("idx", 0))
                    if 1 <= idx <= len(chunk):
                        c = chunk[idx - 1]
                        c["chapter"] = str(item.get("chapter", "")).strip()
                        c["kp"] = str(item.get("kp", "")).strip()
                        c["kp_location"] = str(item.get("kp_location", "")).strip()
                        c["kp_key_point"] = str(item.get("kp_key_point", "")).strip()
                        c["kp_exam_point"] = str(item.get("kp_exam_point", "")).strip()
                        c["kp_frequency"] = str(item.get("kp_frequency", "")).strip()
                        done_data.append(c)
                ok = True
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [X] 批 {start // batch + 1} 失败: {e}")
                time.sleep(3)
        if ok:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(done_data, f, ensure_ascii=False, indent=2)
            print(f"  已完成 {len(done_data)}/{len(data) + len(done_data)}")
        time.sleep(1)

    print(f"\n✅ 完成，共 {len(done_data)} 道，输出: {out_path}")


if __name__ == "__main__":
    main()
