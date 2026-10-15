"""
合并多份题库 Excel 成一个总文件。
用法: python scripts/merge_excel.py
说明: 在脚本里配置要合并的文件路径列表。
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd


# ===== 配置 =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INPUT_FILES = [
    os.path.join(BASE_DIR, "data", "exams", "生化", "生化真题1-3.xlsx"),
    os.path.join(BASE_DIR, "data", "exams", "生化", "生化真题2-3.xlsx"),
    os.path.join(BASE_DIR, "data", "exams", "生化", "生化真题3-3.xlsx"),
]

OUTPUT_FILE = os.path.join(BASE_DIR, "data", "exams", "生化", "生化总题库.xlsx")

# 统一列顺序
COLUMNS = ["年份", "题型", "题号", "题干", "选项A", "选项B", "选项C", "选项D",
           "答案", "解析", "考点", "章节"]


def main():
    all_dfs = []

    for path in INPUT_FILES:
        if not os.path.exists(path):
            print(f"⚠️ 跳过（不存在）: {path}")
            continue
        print(f"📄 读取: {os.path.basename(path)}")
        df = pd.read_excel(path)
        print(f"   - {len(df)} 行")

        # 补齐缺失的列
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        # 只保留 COLUMNS 里的列，按顺序
        df = df[COLUMNS]
        all_dfs.append(df)

    if not all_dfs:
        print("❌ 没有可合并的文件")
        return

    merged = pd.concat(all_dfs, ignore_index=True)

    # 按年份、题型、题号排序
    type_order = {"判断": 1, "选择": 2, "填空": 3, "名词解释": 4, "问答": 5, "简答": 5}
    merged["_type_order"] = merged["题型"].map(type_order).fillna(99)
    merged = merged.sort_values(["年份", "_type_order", "题号"]).drop(columns=["_type_order"])
    merged = merged.reset_index(drop=True)

    print(f"\n✅ 合并完成：{len(merged)} 道题")

    print(f"\n📊 按年份统计：")
    print(merged.groupby("年份").size().to_string())

    print(f"\n📊 按题型统计：")
    print(merged.groupby("题型").size().to_string())

    # 按题干内容去重（真正的重复）
    merged["_stem_key"] = merged["题干"].astype(str).str[:50]
    before = len(merged)
    merged = merged.drop_duplicates(subset=["年份", "题型", "_stem_key"], keep="first")
    merged = merged.drop(columns=["_stem_key"])
    removed = before - len(merged)
    print(f"\n🔁 按题干内容去重，删除 {removed} 条真重复")

    # 检查题号冲突（年份+题型+题号）
    dup = merged.duplicated(subset=["年份", "题型", "题号"], keep=False)
    dup_count = dup.sum()
    if dup_count > 0:
        print(f"\n⚠️ 有 {dup_count} 条题号冲突（不同题但题号相同）：")
        print("   （这些是 OCR 解析问题，前端不受影响，可稍后手工修）")
        # 保存冲突清单
        conflict_path = os.path.splitext(OUTPUT_FILE)[0] + "_题号冲突.txt"
        with open(conflict_path, "w", encoding="utf-8") as f:
            for _, r in merged[dup].sort_values(["年份", "题型", "题号"]).iterrows():
                f.write(f"[{int(r['年份'])}年 {r['题型']} 第{r['题号']}题] {r['题干'][:80]}\n")
        print(f"   冲突清单已保存: {conflict_path}")
    else:
        print(f"\n✅ 没有题号冲突")

    merged.to_excel(OUTPUT_FILE, index=False)
    print(f"\n💾 已保存: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()