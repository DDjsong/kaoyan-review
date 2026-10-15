"""
解析 OCR 输出的 txt，输出结构化 Excel。
用法: python scripts/parse_exam_txt.py <txt路径>
输出: 同目录的 <txt文件名>.xlsx
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd


# ============ 配置 ============

# 题型标题（用于 finditer 切分）
SECTION_PATTERN = re.compile(
    r'^\s*[一二三四五六七八九十]+\s*[、.．]\s*'
    r'(判断题|选择题|单项选择题|填空题|填空体|名词解释|问答题|简答题|论述题)'
    r'[^\n]*$',
    re.MULTILINE,
)

# 用于预处理：把"行内嵌的 section 标题"拆到新行
SECTION_INLINE_PATTERN = re.compile(
    r'([一二三四五六七八九十]+\s*[、.．]\s*'
    r'(?:判断题|选择题|单项选择题|填空题|填空体|名词解释|问答题|简答题|论述题)'
    r'[^\n]{0,40})'
)

YEAR_PATTERN = re.compile(r'(\d{4})\s*年')

# 题号：允许"数字 + 标点"或"数字 + 空格"，只认 1-2 位数字（避免误吃年份）
QUESTION_NUM_PATTERN = re.compile(r'^\s*(\d{1,2})(?:\s*[\.．、，,]\s*|\s+)(.*)$')

# 选项匹配：宽松版
# 匹配字母 A-D，前面不是字母/数字，后面跟"标点/空格/中文"
OPTION_LETTER_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])([A-D])(?=[\s\.．、\)）\>：:，,]|[\u4e00-\u9fff])'
)

# 页眉页脚过滤
FILTER_LINES = [
    re.compile(r'^\s*生物牛牛'),
    re.compile(r'^\s*\d+\s*$'),
    re.compile(r'^\s*=====\s*Page\s+\d+\s*=====\s*$'),
]

TYPE_MAP = {
    "判断题": "判断",
    "选择题": "选择",
    "单项选择题": "选择",
    "填空题": "填空",
    "填空体": "填空",
    "名词解释": "名词解释",
    "问答题": "问答",
    "简答题": "问答",
    "论述题": "问答",
}

# OCR 常见错误修正（可扩展）
OCR_FIXES = [
    ('通风', '痛风'),
    ('核昔酸', '核苷酸'),
    ('核糖核昔酸', '核糖核苷酸'),
    ('碱酸滴定', '酸碱滴定'),
    ('氨基瑞', '氨基端'),
    ('商增', '熵增'),
    ('Waston', 'Watson'),
    ('Cricket', 'Crick'),
]


def is_filtered(line):
    for p in FILTER_LINES:
        if p.search(line):
            return True
    return False


def clean_lines(text):
    """过滤页眉页脚 + 把行内嵌的 section 标题拆到新行"""
    result = []
    for line in text.split('\n'):
        if is_filtered(line):
            continue
        # 尝试拆分行内的 section 标题
        parts = SECTION_INLINE_PATTERN.split(line)
        if len(parts) > 1:
            for part in parts:
                if part.strip():
                    result.append(part)
        else:
            result.append(line)
    return result


def split_by_year(lines):
    papers = []
    current_year = None
    current_lines = []

    for line in lines:
        m = YEAR_PATTERN.search(line)
        if m:
            if current_year is not None and current_lines:
                papers.append({'year': current_year, 'lines': current_lines})
            current_year = int(m.group(1))
            current_lines = []
        else:
            if current_year is not None:
                current_lines.append(line)

    if current_year is not None and current_lines:
        papers.append({'year': current_year, 'lines': current_lines})

    return papers


def split_sections(text):
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
    lines = content.split('\n')
    questions = []
    current_num = None
    current_lines = []

    for line in lines:
        m = QUESTION_NUM_PATTERN.match(line)
        if m:
            # 判断这个数字是否是真正的题号：
            # 如果是纯数字后跟空格/标点，且数字 ≤ 100，视为题号
            num = int(m.group(1))
            body_start = m.group(2).strip()
            # 如果 body 是空的，或者 num > 100，可能是别的内容，不切
            if body_start and num <= 100:
                if current_num is not None:
                    body = '\n'.join(current_lines).strip()
                    if body:
                        questions.append((current_num, body))
                current_num = num
                current_lines = [body_start]
                continue
        if current_num is not None:
            current_lines.append(line)

    if current_num is not None:
        body = '\n'.join(current_lines).strip()
        if body:
            questions.append((current_num, body))

    return questions


def extract_options(body):
    """从选择题题干中提取选项。
    返回 (stem, {'A': ..., 'B': ..., 'C': ..., 'D': ...})
    """
    matches = list(OPTION_LETTER_PATTERN.finditer(body))

    # 找 A、B、C、D 首次出现
    pos = {}
    selected = []
    for m in matches:
        k = m.group(1)
        if k in 'ABCD' and k not in pos:
            pos[k] = len(selected)
            selected.append((k, m))

    # 必须 A、B、C、D 都齐且顺序正确
    if not all(k in pos for k in 'ABCD'):
        return body.strip(), None
    if not (pos['A'] < pos['B'] < pos['C'] < pos['D']):
        return body.strip(), None

    selected.sort(key=lambda x: pos[x[0]])
    selected = selected[:4]

    stem = body[:selected[0][1].start()].strip()
    options = {}
    for i, (k, m) in enumerate(selected):
        start = m.end()
        end = selected[i+1][1].start() if i+1 < len(selected) else len(body)
        options[k] = body[start:end].strip()

    return stem, options


def apply_ocr_fixes(text):
    if not text:
        return text
    for wrong, right in OCR_FIXES:
        text = text.replace(wrong, right)
    return text


def parse_paper(paper):
    year = paper['year']
    text = '\n'.join(paper['lines'])
    sections = split_sections(text)

    rows = []
    for section_type, content in sections:
        questions = split_questions(content)
        for num, body in questions:
            stem = body
            options = None

            if section_type == "选择":
                stem, options = extract_options(body)

            stem = apply_ocr_fixes(stem)

            row = {
                "年份": year,
                "题型": section_type,
                "题号": num,
                "题干": stem,
                "选项A": apply_ocr_fixes(options.get('A', '')) if options else '',
                "选项B": apply_ocr_fixes(options.get('B', '')) if options else '',
                "选项C": apply_ocr_fixes(options.get('C', '')) if options else '',
                "选项D": apply_ocr_fixes(options.get('D', '')) if options else '',
                "答案": "",
                "解析": "",
                "考点": "",
                "章节": "",
            }
            rows.append(row)
    return rows


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/parse_exam_txt.py <txt路径>")
        sys.exit(1)

    txt_path = sys.argv[1]
    if not os.path.exists(txt_path):
        print(f"❌ 文件不存在: {txt_path}")
        sys.exit(1)

    print(f"📄 读取: {txt_path}")
    with open(txt_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    lines = clean_lines(raw_text)
    print(f"📝 清理后行数: {len(lines)}")

    papers = split_by_year(lines)
    print(f"📚 识别到 {len(papers)} 套试卷:")
    for p in papers:
        print(f"  - {p['year']} 年（{len(p['lines'])} 行）")

    all_rows = []
    for paper in papers:
        rows = parse_paper(paper)
        all_rows.extend(rows)

    if not all_rows:
        print("\n⚠️ 没有解析到任何题目。请检查 txt 文件是否包含年份标题。")
        return

    df = pd.DataFrame(all_rows)

    # 统计：选择题里选项完整 vs 缺失
    choice_df = df[df['题型'] == '选择']
    choice_with_options = choice_df[choice_df['选项A'] != '']
    choice_without = choice_df[choice_df['选项A'] == '']

    print(f"\n✅ 共解析 {len(df)} 道题")
    print(f"\n📊 按年份统计:")
    print(df.groupby('年份').size().to_string())
    print(f"\n📊 按题型统计:")
    print(df.groupby('题型').size().to_string())

    print(f"\n📊 选择题选项完整度:")
    print(f"  完整（4 个选项都拆开）: {len(choice_with_options)} 道")
    print(f"  缺失（选项没拆出）: {len(choice_without)} 道")

    if len(choice_without) > 0:
        print(f"\n  ⚠️ 选项未拆出的题目（年份/题号）：")
        for _, r in choice_without.iterrows():
            print(f"    - {int(r['年份'])}年 第{r['题号']}题")

    out_path = os.path.splitext(txt_path)[0] + ".xlsx"
    df.to_excel(out_path, index=False)
    print(f"\n💾 已保存: {out_path}")


if __name__ == "__main__":
    main()