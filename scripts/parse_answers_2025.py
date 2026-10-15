"""
2025 年答案专用解析（格式不规则：选择答案浓缩成 '1-6：DBCDBD'，笔记式）。
输出: 年份, 题型, 题号, 答案, 解析
"""
import os, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd

PATH = r"D:\PythonProject\deepseek_AI_project\data\exams\生化答案\25年704生化真题详解.txt"
YEAR = 2025

with open(PATH, encoding='utf-8') as f:
    lines = f.read().split('\n')

# 定位各题型区块（按行首 "一、选择题" 式标题匹配）
SECTION_HEADER = re.compile(r'^\s*[一二三四五六七八九十]+\s*[、,．.]\s*(选择|填空|名词解释|简答|判断|问答|论述)')

def find_section(kw):
    for i, ln in enumerate(lines):
        m = SECTION_HEADER.match(ln)
        if m and m.group(1) in kw:
            return i
    return None

idx_choice = find_section('选择题')
idx_blank = find_section('填空题')
idx_noun = find_section('名词解释')
idx_short = find_section('简答题')
bounds = sorted([x for x in [idx_choice, idx_blank, idx_noun, idx_short] if x is not None]) + [len(lines)]

def section_lines(idx):
    end = next((b for b in bounds if b > idx), len(lines))
    return lines[idx+1:end]

rows = []

# ---- 选择题 ----
choice_lines = section_lines(idx_choice)
# 找到 "1-6： DBCDBD"
letters = []
for ln in choice_lines:
    m = re.search(r'(\d+)\s*-\s*(\d+)\s*[:：]\s*([A-Da-d][A-Da-d\s]*)\s*$', ln)
    if m:
        letters = [c for c in re.findall(r'[A-Da-d]', m.group(3))]
        break
if not letters:
    # 回退：找连续大写字母串
    for ln in choice_lines:
        m = re.search(r'[:：]\s*([A-Da-d]{4,})', ln)
        if m:
            letters = list(m.group(1).upper())
            break
# 逐题解析（仅部分题有，编号 1/2/3/6 等）
expl_map = {}
for ln in choice_lines:
    m = re.match(r'^\s*(\d+)\s*[\.．、]\s*(.*)$', ln)
    if m and int(m.group(1)) <= len(letters):
        expl_map[int(m.group(1))] = m.group(2).strip()
for i, ch in enumerate(letters, start=1):
    rows.append({"年份": YEAR, "题型": "选择", "题号": i,
                 "答案": ch.upper(), "解析": expl_map.get(i, "")})
print(f"选择: {len(letters)} 条 -> {letters}")

# ---- 填空题（取每个题号第一次出现作为答案，后续同号视为笔记并入解析）----
blank_lines = section_lines(idx_blank)
blank_ans = {}
blank_note = {}
for ln in blank_lines:
    m = re.match(r'^\s*(\d+)\s*[\.．、]\s*(.*)$', ln)
    if not m:
        continue
    n = int(m.group(1))
    txt = m.group(2).strip()
    if n not in blank_ans:
        blank_ans[n] = txt
    else:
        blank_note[n] = (blank_note.get(n, "") + " " + txt).strip()
for n in sorted(blank_ans):
    rows.append({"年份": YEAR, "题型": "填空", "题号": n,
                 "答案": blank_ans[n], "解析": blank_note.get(n, "")})
print(f"填空: {len(blank_ans)} 条")

# ---- 名词解释 ----
noun_lines = section_lines(idx_noun)
for ln in noun_lines:
    m = re.match(r'^\s*(\d+)\s*[\.．、]\s*(.*)$', ln)
    if m:
        n = int(m.group(1))
        txt = m.group(2).strip()
        # 拆分"名词：解释"
        if '：' in txt or ':' in txt:
            parts = re.split(r'[:：]', txt, 1)
            ans = parts[0].strip()
            expl = parts[1].strip() if len(parts) > 1 else ""
        else:
            ans, expl = txt, ""
        rows.append({"年份": YEAR, "题型": "名词解释", "题号": n, "答案": ans, "解析": expl})
print(f"名词解释: {sum(1 for r in rows if r['题型']=='名词解释')} 条")

# ---- 简答题（题号单独成行，答案在后续行；也可能同题号后接"与XX年相似"）----
short_lines = section_lines(idx_short)
cur = None
short_buf = {}
for ln in short_lines:
    m = re.match(r'^\s*(\d+)\s*[\.．、]\s*(.*)$', ln)
    if m:
        n = int(m.group(1))
        txt = m.group(2).strip()
        if txt.startswith('与') and '相似' in txt:
            # 该题只有"与XX年相似"的提示，答案留备注
            short_buf[n] = txt
        else:
            short_buf[n] = txt
        cur = n
    else:
        if cur is not None and ln.strip():
            short_buf[cur] = (short_buf.get(cur, "") + "\n" + ln.strip()).strip()
for n in sorted(short_buf):
    rows.append({"年份": YEAR, "题型": "问答", "题号": n, "答案": short_buf[n], "解析": ""})
print(f"简答: {len(short_buf)} 条")

df = pd.DataFrame(rows)
out = os.path.splitext(PATH)[0] + ".xlsx"
df.to_excel(out, index=False)
print(f"\n✅ 共 {len(df)} 条 -> {out}")
print(df.groupby('题型').size().to_string())
