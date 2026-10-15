"""
健壮的答案解析器 v2 —— 处理 11-15 / 16 / 17 / 18-19 / 20-24 等不同格式的答案 txt。
输出与 parse_answer_txt.py 一致的 Excel: 年份, 题型, 题号(题型内局部编号), 答案, 解析。
用法: python scripts/parse_answers_v2.py <txt路径> [输出xlsx路径]
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

# ---------- 常量 ----------
TYPE_MAP = {
    "判断": "判断", "选择": "选择", "单项选择": "选择", "填空": "填空",
    "名词解释": "名词解释", "问答": "问答", "简答": "问答", "论述": "问答",
}

# 题型标题（"题"字可选，兼容 "三、填空" / "四、简答"）
SECTION_PATTERN = re.compile(
    r'^\s*[一二三四五六七八九十]+\s*[、.．]\s*'
    r'(判断|选择|单项选择|填空|名词解释|问答|简答|论述)题?[^\n]*$'
)

YEAR_TITLE_PATTERN = re.compile(r'(\d{4})\s*年')

QNUM = re.compile(r'^\s*(\d{1,3})\s*[\.．、]\s*(.*)$')

ANSWER_PREFIX = re.compile(r'^答案\s*[:：]\s*')


def is_year_title(line):
    if "年" not in line:
        return False
    if ("答案" not in line) and ("真题" not in line) and ("参考" not in line):
        return False
    return bool(YEAR_TITLE_PATTERN.search(line))


def strip_answer_prefix(body):
    return ANSWER_PREFIX.sub('', body).strip()


def split_explanation(body):
    """把 '解析：xxx'（可带 ◦/• 前缀，可位于行中）从 body 拆出。返回 (body, explanation)。"""
    m = re.search(r'解析\s*[:：]\s*', body)
    if m:
        left = body[:m.start()].rstrip('◦• \t')
        expl = body[m.end():].strip()
        return left.strip(), expl
    return body.rstrip('◦• \t').strip(), ""


def extract_judgment(body):
    body = strip_answer_prefix(body)
    body, expl = split_explanation(body)
    body = body.strip()
    ans = ""
    if body:
        c = body[0]
        if c in "√✓✔vV对":
            ans = "√"
        elif c in "×xX✗✘错":
            ans = "×"
        rest = body[1:].lstrip("。.．、)）】] ")
        expl = (rest + " " + expl).strip() if rest else expl
    return ans, expl


def extract_choice(body):
    body = strip_answer_prefix(body)
    body, expl = split_explanation(body)
    body = body.strip()
    # 尝试拆出单个字母答案 A-D
    m = re.match(r'^([A-Da-d])\s*[\.．。、\)）]?\s*(.*)$', body, re.S)
    if m:
        ans = m.group(1).upper()
        rest = m.group(2).strip()
        expl = (rest + " " + expl).strip() if rest else expl
        return ans, expl
    # 无字母：整个 body 当作答案（文字型选择题）
    return body, expl


def extract_blank(body):
    """标准填空题：答案=填空值列表，末尾单个括号说明移到解析。"""
    body = strip_answer_prefix(body)
    body, expl = split_explanation(body)
    body = body.strip()
    # 仅当整个 body 只有一个（结尾）括号时才视为"说明"拆出
    if body.count('（') == 1 and body.endswith('）'):
        i = body.find('（')
        ans = body[:i].strip()
        paren = body[i + 1:-1].strip()
        if ans:
            expl = (paren + " " + expl).strip() if paren else expl
            return ans, expl
    return body, expl


def extract_inline_blank(body):
    """2015/2018 式填空题：答案内嵌在题干括号中。返回 (答案串, 解析)。"""
    body, expl = split_explanation(body)
    answers = re.findall(r'（([^（）]*)）', body)
    ans = "、".join(a.strip() for a in answers if a.strip())
    return ans, expl


def is_inline_blank(body):
    """判断某填空题是否为"题干内嵌答案"格式。"""
    if ANSWER_PREFIX.match(body.strip()):
        return False
    if body.count('（') < 2:
        return False
    first = body.find('（')
    return len(body[:first].strip()) >= 6


def parse_section(section_type, lines):
    """解析一个题型区块，返回 [(题号local, 答案, 解析), ...]"""
    candidates = []  # (line_idx, num, body)
    for i, ln in enumerate(lines):
        m = QNUM.match(ln)
        if m:
            candidates.append((i, int(m.group(1)), m.group(2).strip()))

    if not candidates:
        return []

    base = candidates[0][1]

    # 问答/简答/名词解释：题号可能被答案内子编号污染，用紧凑窗口过滤
    if section_type in ("问答", "名词解释"):
        valid = [c for c in candidates if base <= c[1] <= base + 20]
    else:
        valid = candidates

    questions = []
    for idx, (li, num, body0) in enumerate(valid):
        local = num - base + 1
        end = valid[idx + 1][0] if idx + 1 < len(valid) else len(lines)
        body_lines = [body0]
        for j in range(li + 1, end):
            body_lines.append(lines[j])

        if section_type == "判断":
            ans, expl = extract_judgment(" ".join(body_lines))
        elif section_type == "选择":
            ans, expl = extract_choice(" ".join(body_lines))
        elif section_type == "填空":
            joined = " ".join(body_lines)
            if is_inline_blank(joined):
                ans, expl = extract_inline_blank(joined)
            else:
                ans, expl = extract_blank(joined)
        else:  # 问答/名词解释
            full = "\n".join(body_lines).strip()
            m = re.search(r'答案\s*[:：]\s*', full)
            if m:
                ans = full[m.end():].strip()
            else:
                ans = full
            expl = ""

        questions.append((local, ans.strip(), expl.strip()))

    return questions


def parse_file(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    lines = raw.split('\n')

    papers = []
    cur_year = None
    cur_lines = []
    for ln in lines:
        if is_year_title(ln):
            if cur_year is not None and cur_lines:
                papers.append((cur_year, cur_lines))
            m = YEAR_TITLE_PATTERN.search(ln)
            cur_year = int(m.group(1))
            cur_lines = []
        else:
            if cur_year is not None:
                cur_lines.append(ln)
    if cur_year is not None and cur_lines:
        papers.append((cur_year, cur_lines))

    all_rows = []
    for year, plines in papers:
        sec_idx = []
        for i, ln in enumerate(plines):
            if SECTION_PATTERN.match(ln):
                sec_idx.append(i)
        if not sec_idx:
            continue

        for si, pos in enumerate(sec_idx):
            header = plines[pos]
            m = SECTION_PATTERN.match(header)
            section_type = TYPE_MAP.get(m.group(1), m.group(1))
            end = sec_idx[si + 1] if si + 1 < len(sec_idx) else len(plines)
            content = plines[pos + 1:end]
            for local, ans, expl in parse_section(section_type, content):
                all_rows.append({
                    "年份": year, "题型": section_type, "题号": local,
                    "答案": ans, "解析": expl,
                })
    return all_rows


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/parse_answers_v2.py <txt路径> [输出xlsx路径]")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)

    rows = parse_file(path)
    if not rows:
        print("⚠️ 没解析到内容")
        return
    df = pd.DataFrame(rows)
    print(f"✅ 共 {len(df)} 条答案")
    print("\n📊 按年份:")
    print(df.groupby('年份').size().to_string())
    print("\n📊 按题型:")
    print(df.groupby('题型').size().to_string())
    print("\n📋 判断题答案取值:", sorted(set(str(a) for a in df[df['题型'] == '判断']['答案'])))
    letters = sorted(set(str(a) for a in df[df['题型'] == '选择']['答案'] if str(a) in 'ABCD'))
    text_ans = df[(df['题型'] == '选择') & (~df['答案'].astype(str).isin(['A', 'B', 'C', 'D']))]
    print(f"📋 选择题字母答案: {letters}；文字型答案 {len(text_ans)} 条")
    blank_empty = int(df[df['题型'] == '填空']['答案'].astype(str).str.strip().isin(['', 'nan', 'None']).sum())
    print(f"📋 填空题空答案: {blank_empty} 条")

    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(path)[0] + ".xlsx"
    df.to_excel(out, index=False)
    print(f"\n💾 已保存: {out}")


if __name__ == "__main__":
    main()
