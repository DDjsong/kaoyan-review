"""
解析答案 txt，输出结构化 Excel。
用法: python scripts/parse_answer_txt.py <txt路径>
输出: 同目录的 <txt文件名>.xlsx
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd


# 年份标题
YEAR_PATTERN = re.compile(r'(\d{4})\s*年')

# 题型标题
SECTION_PATTERN = re.compile(
    r'^\s*[一二三四五六七八九十]+\s*[、.．]\s*'
    r'(判断题|选择题|单项选择题|填空题|名词解释|问答题|简答题|论述题)'
    r'[^\n]*$',
    re.MULTILINE,
)

# 题号（行首）
QUESTION_NUM_PATTERN = re.compile(r'^\s*(\d+)\s*[\.．、]\s*(.*)$')

# 提取 "解析：xxx"
EXPLANATION_PATTERN = re.compile(r'解析[:：]\s*(.*)', re.DOTALL)

TYPE_MAP = {
    "判断题": "判断",
    "选择题": "选择",
    "单项选择题": "选择",
    "填空题": "填空",
    "名词解释": "名词解释",
    "问答题": "问答",
    "简答题": "问答",
    "论述题": "问答",
}


def is_year_title(line):
    """判断是否年份标题行，如 '南开大学2000年生物化学考研真题答案'"""
    if "年" not in line:
        return False
    if "答案" not in line and "真题" not in line:
        return False
    m = YEAR_PATTERN.search(line)
    return bool(m)


def split_by_year(lines):
    """按年份标题切分"""
    papers = []
    current_year = None
    current_lines = []

    for line in lines:
        if is_year_title(line):
            if current_year is not None and current_lines:
                papers.append({'year': current_year, 'lines': current_lines})
            m = YEAR_PATTERN.search(line)
            current_year = int(m.group(1))
            current_lines = []
        else:
            if current_year is not None:
                current_lines.append(line)

    if current_year is not None and current_lines:
        papers.append({'year': current_year, 'lines': current_lines})

    return papers


def split_sections(text):
    """按题型标题切分"""
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return []
    sections = []
    for i, m in enumerate(matches):
        raw_type = m.group(1)
        section_type = TYPE_MAP.get(raw_type, raw_type)
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections.append((section_type, content))
    return sections


def split_questions(content):
    """按题号切分，返回 [(题号, 内容), ...]"""
    lines = content.split('\n')
    questions = []
    current_num = None
    current_lines = []

    for line in lines:
        m = QUESTION_NUM_PATTERN.match(line)
        if m:
            num = int(m.group(1))
            body = m.group(2).strip()
            if body and num <= 200:  # 题号不会超过 200
                if current_num is not None:
                    body_text = '\n'.join(current_lines).strip()
                    if body_text:
                        questions.append((current_num, body_text))
                current_num = num
                current_lines = [body]
                continue
        if current_num is not None:
            current_lines.append(line)

    if current_num is not None:
        body_text = '\n'.join(current_lines).strip()
        if body_text:
            questions.append((current_num, body_text))

    return questions


def extract_answer_explanation(section_type, body):
    """从题目内容中提取答案和解析"""
    body = body.strip()

    # 提取解析
    explanation = ""
    m = EXPLANATION_PATTERN.search(body)
    if m:
        explanation = m.group(1).strip()
        body = body[:m.start()].strip()

    answer = body.strip()

    # 判断题：答案应该是 √ 或 ×
    if section_type == "判断":
        # 判断答案
        if answer.startswith("√") or answer.startswith("×"):
            pass
        elif answer.startswith("对"):
            answer = "√"
        elif answer.startswith("错"):
            answer = "×"

    # 选择题：答案应该是 a/b/c/d
    elif section_type == "选择":
        # 提取单个字母
        am = re.match(r'^([a-dA-D])\b', answer)
        if am:
            answer = am.group(1).lower()

    return answer, explanation


def parse_paper(paper):
    year = paper['year']
    text = '\n'.join(paper['lines'])
    sections = split_sections(text)

    rows = []
    for section_type, content in sections:
        questions = split_questions(content)
        for local_order, (num, body) in enumerate(questions, start=1):
            answer, explanation = extract_answer_explanation(section_type, body)
            rows.append({
                "年份": year,
                "题型": section_type,
                "题号": local_order,  # 按题型内顺序号（1, 2, 3...）
                "答案": answer,
                "解析": explanation,
            })
    return rows


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/parse_answer_txt.py <txt路径>")
        sys.exit(1)

    txt_path = sys.argv[1]
    if not os.path.exists(txt_path):
        print(f"❌ 文件不存在: {txt_path}")
        sys.exit(1)

    print(f"📄 读取: {txt_path}")
    with open(txt_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    lines = raw_text.split('\n')
    papers = split_by_year(lines)
    print(f"📚 识别到 {len(papers)} 个年份")
    for p in papers:
        print(f"  - {p['year']} 年（{len(p['lines'])} 行）")

    all_rows = []
    for paper in papers:
        rows = parse_paper(paper)
        all_rows.extend(rows)

    if not all_rows:
        print("⚠️ 没解析到内容")
        return

    df = pd.DataFrame(all_rows)
    print(f"\n✅ 共 {len(df)} 条答案")
    print(f"\n📊 按年份:")
    print(df.groupby('年份').size().to_string())
    print(f"\n📊 按题型:")
    print(df.groupby('题型').size().to_string())

    out_path = os.path.splitext(txt_path)[0] + ".xlsx"
    df.to_excel(out_path, index=False)
    print(f"\n💾 已保存: {out_path}")


if __name__ == "__main__":
    main()