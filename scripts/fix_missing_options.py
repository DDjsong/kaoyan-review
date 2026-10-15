"""
对总题库里"选项缺失"的选择题做二次拆分。
能拆出来的拆，拆不出来的标记为 answer_mode=self（自评模式）。
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE_DIR, "data", "exams", "生化", "生化总题库.xlsx")

OPTION_PATTERN = re.compile(r'(?<![A-Za-z0-9])([a-dA-D])\s*[\.．、\)）\]:：,，]\s*')
LEADING_JUNK = re.compile(r'^[\s\.．、,，\)）\]】>：:]+')


def is_blank(v):
    return pd.isna(v) or str(v).strip() in ("", "nan", "None")


def try_split_letter_options(text):
    """从文本中拆出 A. B. C. D. 选项"""
    matches = list(OPTION_PATTERN.finditer(text))
    if len(matches) < 4:
        return None

    selected = []
    seen = set()
    for m in matches:
        letter = m.group(1).upper()
        if letter in 'ABCD' and letter not in seen:
            seen.add(letter)
            selected.append((letter, m))

    if len(selected) != 4:
        return None
    if [s[0] for s in selected] != ['A', 'B', 'C', 'D']:
        return None

    stem = text[:selected[0][1].start()].strip()
    opts = []
    for i, (letter, m) in enumerate(selected):
        start = m.end()
        end = selected[i+1][1].start() if i+1 < len(selected) else len(text)
        opts.append(text[start:end].strip())
    if sum(1 for o in opts if len(o) > 1) < 3:
        return None
    return stem, opts


def clean_opt(s):
    if is_blank(s):
        return ""
    s = str(s).strip()
    s = re.sub(r'^[A-Da-d]\s*[\.．、\)）\]:：,，]\s*', '', s)
    s = LEADING_JUNK.sub('', s)
    return re.sub(r'\s+', ' ', s).strip()


def main():
    df = pd.read_excel(PATH)
    print(f"📊 总题数: {len(df)}")

    # 增加 answer_mode 列（默认空）
    if "answer_mode" not in df.columns:
        df["answer_mode"] = ""
    if "user_answer" not in df.columns:
        df["user_answer"] = ""

    fixed_count = 0
    self_mode_count = 0
    issue_list = []

    for idx, row in df.iterrows():
        if row.get("题型") != "选择":
            continue

        # 检查 4 个选项是否全空
        opts = [row.get(c) for c in ["选项A", "选项B", "选项C", "选项D"]]
        if not all(is_blank(o) for o in opts):
            continue

        # 尝试从题干拆
        stem = str(row.get("题干") or "")
        result = try_split_letter_options(stem)
        if result:
            new_stem, new_opts = result
            df.at[idx, "题干"] = new_stem
            for c, v in zip(["选项A", "选项B", "选项C", "选项D"], new_opts):
                df.at[idx, c] = clean_opt(v)
            fixed_count += 1
        else:
            # 拆不出来，标记为自评模式
            df.at[idx, "answer_mode"] = "self"
            self_mode_count += 1
            issue_list.append((int(row["年份"]), int(row["题号"]), stem[:80]))

    print(f"\n✅ 修复完成")
    print(f"  自动拆出选项: {fixed_count} 道")
    print(f"  标记为自评模式: {self_mode_count} 道")

    if issue_list:
        print(f"\n📋 自评模式清单（这些题在刷题时会显示'记得/模糊/忘记'按钮）：")
        for y, n, s in issue_list:
            print(f"  - {y}年 第{n}题 {s}")

    df.to_excel(PATH, index=False)
    print(f"\n💾 已保存: {PATH}")


if __name__ == "__main__":
    main()