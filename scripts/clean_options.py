"""
对解析生成的 Excel 做后处理：
1. 把字符串 "nan"/"None" 等归一化为空
2. 从题干里拆出选项（支持 A. A) A） A、 a. a) 等格式）
3. 清洗选项开头多余标点
4. 输出问题清单

用法: python scripts/clean_options.py <xlsx路径>
"""
import os
import re
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import numpy as np


# ============ 常量 ============

NULL_TOKENS = {'', 'nan', 'NaN', 'NAN', 'None', 'none', 'NULL', 'null'}

# 选项前缀：字母 + 标点（. ） ) 、 ： , 等）
# 前面不能是字母/数字，避免误匹配 "D1" 中的 D
OPTION_LETTER_PATTERN = re.compile(
    r'(?<![A-Za-z0-9])([a-dA-D])\s*[\.．、\)）\]:：,，]\s*'
)

# 4 个 ")" 分隔的选项
OPTION_PAREN_PATTERN = re.compile(
    r'^(.*?)\s*[\)）]\s*(.+?)\s*[\)）]\s*(.+?)\s*[\)）]\s*(.+?)\s*[\)）]\s*(.+)$'
)

# 开头清洗的标点
LEADING_JUNK = re.compile(r'^[\s\.．、,，\)）\]】>：:]+')


def is_empty(val):
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    return str(val).strip() in NULL_TOKENS


def clean_option_text(s):
    """清洗单个选项文本"""
    if is_empty(s):
        return ""
    s = str(s).strip()
    # 去开头的 "A. A) A） A、 a. a)" 等前缀
    s = re.sub(r'^[A-Da-d]\s*[\.．、\)）\]:：,，]\s*', '', s)
    s = LEADING_JUNK.sub('', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def try_split_letter_options(stem):
    """
    支持 a. b. c. d. / A. B. C. D. / a) b) c) d) / a、b、c、d、 等格式。
    返回 (new_stem, [A, B, C, D]) 或 None
    """
    if not stem:
        return None

    matches = list(OPTION_LETTER_PATTERN.finditer(stem))
    if len(matches) < 4:
        return None

    # 取 A、B、C、D 各自首次出现
    selected = []
    seen = set()
    for m in matches:
        letter = m.group(1).upper()
        if letter in 'ABCD' and letter not in seen:
            seen.add(letter)
            selected.append((letter, m))

    if len(selected) != 4:
        return None

    # 检查顺序
    letters = [s[0] for s in selected]
    if letters != ['A', 'B', 'C', 'D']:
        return None

    stem_only = stem[:selected[0][1].start()].strip()
    opts = []
    for i, (letter, m) in enumerate(selected):
        start = m.end()
        end = selected[i + 1][1].start() if i + 1 < len(selected) else len(stem)
        opts.append(stem[start:end].strip())

    # 至少 3 个选项长度 > 1（避免误拆）
    if sum(1 for o in opts if len(o) > 1) < 3:
        return None

    return stem_only, opts


def try_split_paren_options(stem):
    """支持 xxx )aaa )bbb )ccc )ddd 格式（4 个右括号分隔）"""
    if not stem:
        return None
    m = OPTION_PAREN_PATTERN.match(stem)
    if not m:
        return None
    prefix = m.group(1).strip()
    opts = [m.group(2), m.group(3), m.group(4), m.group(5)]
    if sum(1 for o in opts if len(o.strip()) > 1) < 3:
        return None
    return prefix, [o.strip() for o in opts]


def split_options_from_stem(stem):
    """尝试从题干里拆出选项。返回 (new_stem, [A,B,C,D]) 或 None"""
    if not stem:
        return None

    # 优先字母+标点格式
    result = try_split_letter_options(stem)
    if result:
        return result

    # 其次 4 个 ")"
    result = try_split_paren_options(stem)
    if result:
        return result

    return None


def clean_dataframe(df):
    """清洗 DataFrame，返回 (新df, 问题清单)"""
    issues = []
    fixed_count = 0

    for idx, row in df.iterrows():
        if row.get('题型') != '选择':
            continue

        year = int(row.get('年份')) if not is_empty(row.get('年份')) else 0
        num = int(row.get('题号')) if not is_empty(row.get('题号')) else 0
        stem = str(row.get('题干') or '')

        # 判断现有 4 个选项是否为空（考虑 "nan" 字符串）
        cols = ['选项A', '选项B', '选项C', '选项D']
        old_opts = [clean_option_text(row.get(c)) for c in cols]
        has_opts = any(o for o in old_opts)

        if has_opts:
            # 有选项，只清洗
            for c, v in zip(cols, old_opts):
                df.at[idx, c] = v
            # 检查是否有空
            empty = [c for c, v in zip(cols, old_opts) if not v]
            if empty:
                issues.append((year, num, f'缺{empty}', stem[:80]))
        else:
            # 选项为空，尝试从题干拆
            result = split_options_from_stem(stem)
            if result:
                new_stem, new_opts = result
                df.at[idx, '题干'] = new_stem
                for c, v in zip(cols, new_opts):
                    df.at[idx, c] = clean_option_text(v)
                fixed_count += 1
            else:
                # 完全拆不出来，清空四列，记入清单
                for c in cols:
                    df.at[idx, c] = ''
                issues.append((year, num, '无法自动拆分', stem[:80]))

    return df, issues, fixed_count


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/clean_options.py <xlsx路径>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)

    print(f"📄 读取: {path}")
    df = pd.read_excel(path)

    print(f"📊 总题数: {len(df)}")
    choice_df_before = df[df['题型'] == '选择']
    print(f"📊 选择题: {len(choice_df_before)}")

    df, issues, fixed_count = clean_dataframe(df)

    print(f"\n🔧 本次从题干拆出选项: {fixed_count} 道")

    # 重新统计
    choice_df = df[df['题型'] == '选择']
    complete = choice_df[
        (choice_df['选项A'].astype(str).str.strip() != '') &
        (choice_df['选项B'].astype(str).str.strip() != '') &
        (choice_df['选项C'].astype(str).str.strip() != '') &
        (choice_df['选项D'].astype(str).str.strip() != '')
    ]
    still_bad = len(choice_df) - len(complete)

    print(f"\n✅ 清洗完成")
    print(f"  选项完整: {len(complete)} 道")
    print(f"  仍需人工: {still_bad} 道")

    # 保存
    df.to_excel(path, index=False)
    print(f"\n💾 已覆盖: {path}")

    # 问题清单
    if issues:
        issue_path = os.path.splitext(path)[0] + "_issues.txt"
        with open(issue_path, "w", encoding="utf-8") as f:
            f.write(f"共 {len(issues)} 道题需要人工检查：\n\n")
            for year, num, reason, snippet in issues:
                f.write(f"[{year}年 第{num}题] {reason}\n  {snippet}\n\n")
        print(f"📋 问题清单: {issue_path}")

    # 打印前 30 条需人工的
    if still_bad > 0:
        print(f"\n⚠️ 仍需人工的题目（前 30 条）：")
        count = 0
        for _, r in choice_df.iterrows():
            empty = []
            for c in ['选项A', '选项B', '选项C', '选项D']:
                v = r[c]
                if is_empty(v) or str(v).strip() == '':
                    empty.append(c)
            if empty:
                print(f"  - {int(r['年份'])}年 第{int(r['题号'])}题 缺{empty}")
                count += 1
                if count >= 30:
                    break


if __name__ == "__main__":
    main()