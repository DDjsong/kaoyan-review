import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE_DIR, "data", "exams", "生化", "生化总题库.xlsx")

df = pd.read_excel(PATH)
choice = df[df["题型"] == "选择"].copy()


# 选项全空的
def is_blank(v):
    return pd.isna(v) or str(v).strip() in ("", "nan", "None")


missing = choice[
    choice["选项A"].apply(is_blank) &
    choice["选项B"].apply(is_blank) &
    choice["选项C"].apply(is_blank) &
    choice["选项D"].apply(is_blank)
    ]

# 部分空的
partial = choice[
    ~(choice["选项A"].apply(is_blank) &
      choice["选项B"].apply(is_blank) &
      choice["选项C"].apply(is_blank) &
      choice["选项D"].apply(is_blank))
    &
    (choice["选项A"].apply(is_blank) |
     choice["选项B"].apply(is_blank) |
     choice["选项C"].apply(is_blank) |
     choice["选项D"].apply(is_blank))
    ]

print(f"总选择题: {len(choice)}")
print(f"选项全空（原题库就没有）: {len(missing)}")
print(f"选项部分空（OCR 问题）: {len(partial)}")

if len(missing) > 0:
    print(f"\n📋 选项全空清单（前 20 条）：")
    print(missing[["年份", "题号", "题干"]].head(20).to_string())

    # 保存清单
    out = os.path.join(BASE_DIR, "data", "exams", "生化", "选项缺失选择题.txt")
    with open(out, "w", encoding="utf-8") as f:
        for _, r in missing.iterrows():
            f.write(f"[{int(r['年份'])}年 第{int(r['题号'])}题] {r['题干'][:100]}\n")
    print(f"\n💾 清单已保存: {out}")

if len(partial) > 0:
    print(f"\n⚠️ 部分空的清单（前 20 条）：")
    print(partial[["年份", "题号", "题干"]].head(20).to_string())