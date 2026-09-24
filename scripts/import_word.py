import os
import re
import sys
import json
from docx import Document
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_docx(folder):
    if not os.path.isdir(folder):
        return None
    for f in os.listdir(folder):
        if f.endswith(".docx") and not f.startswith("~$"):
            return os.path.join(folder, f)
    return None


def load_text(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def parse_chapters(full_text):
    """识别章节标题，过滤掉答案里的'第19章题目'这种误识别"""
    chapters = []
    for m in re.finditer(r"(?m)^#*\s*第(\d+)章[^\n]*$", full_text):
        line = m.group().strip().lstrip("#").strip()
        # 过滤条件：长度超过 40，或含"题目/答案/考点/涉及知识点"等词，都不是章节标题
        if len(line) > 40:
            continue
        if any(bad in line for bad in ["题目", "答案", "考点", "涉及知识点", "：", ":"]):
            continue
        chapters.append((m.start(), line))
    return chapters


def parse_questions(full_text):
    full_text = re.sub(r"=+\s*Page\s*\d+\s*=+", "\n", full_text)

    chapters = parse_chapters(full_text)

    q_pattern = re.compile(r"(?:^|\n)(?:\d+\.\s*)?[（(](\d{4})\s*年[)）]")
    q_matches = list(q_pattern.finditer(full_text))

    questions = []
    for i, m in enumerate(q_matches):
        start = m.start()
        end = q_matches[i + 1].start() if i + 1 < len(q_matches) else len(full_text)
        block = full_text[start:end].strip()
        year = int(m.group(1))

        # 章节：取位置在该题之前、最近的一个
        chapter = "未分类"
        for cpos, cname in chapters:
            if cpos < start:
                chapter = cname
            else:
                break

        block_clean = re.sub(r"^\d+\.\s*", "", block).strip()

        parts = re.split(r"(?:完整答案|·答案|答案)[:：]", block_clean, maxsplit=1)
        stem_part = parts[0].strip()
        answer_part = parts[1].strip() if len(parts) > 1 else ""

        # 考点
        kp_text = ""
        m1 = re.search(r"考点[:：]\s*([^\n]+)", stem_part)
        if m1:
            kp_text = m1.group(1).strip().rstrip("。")
        # 涉及知识点
        m2 = re.search(r"[·•]?\s*涉及知识点[:：]\s*([^\n]+)", stem_part)
        if m2:
            text = m2.group(1).strip().rstrip("。")
            kp_text = (kp_text + "、" + text) if kp_text else text

        # 清洗题干
        stem = stem_part
        stem = re.sub(r"考点[:：][^\n]*", "", stem)
        stem = re.sub(r"[·•]?\s*涉及知识点[:：][^\n]*", "", stem)
        stem = re.sub(r"^[（(]\d{4}\s*年[)）]\s*", "", stem)
        stem = re.sub(r"^\d+\.\s*", "", stem)
        stem = re.sub(r"\s+", " ", stem).strip()

        questions.append({
            "year": year,
            "stem": stem,
            "kp_text": kp_text,
            "answer": answer_part.strip(),
            "chapter": chapter,
        })

    return questions


def norm_text(t):
    """去掉所有非中英文和数字的字符，用于模糊匹配"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", t)


def dedup(questions):
    """按题干内容去重（不管年份），题干完全一致视为重复"""
    seen = set()
    uniq = []
    dup_count = 0
    for q in questions:
        key = norm_text(q["stem"])
        if key in seen:
            dup_count += 1
            continue
        seen.add(key)
        uniq.append(q)
    return uniq, dup_count


if __name__ == "__main__":
    folder = os.path.join(BASE_DIR, "data", "questions")
    path = find_docx(folder)
    if not path:
        print(f"❌ 在 {folder} 里没有找到 .docx 文件")
        sys.exit(1)

    print(f"📄 读取: {path}")
    text = load_text(path)
    print(f"📝 总字符数: {len(text)}")

    questions = parse_questions(text)
    print(f"✅ 原始解析: {len(questions)} 道")

    questions, dup_count = dedup(questions)
    print(f"🔁 去重 {dup_count} 道，剩 {len(questions)} 道\n")

    chap_counter = Counter(q["chapter"] for q in questions)
    print("📚 各章节题目数:")
    for chap, cnt in chap_counter.most_common():
        print(f"  {chap}: {cnt}")

    out_dir = os.path.join(BASE_DIR, "data", "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "parsed_questions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存: {out_path}")