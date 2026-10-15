import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTION_PATH = os.path.join(BASE_DIR, "data", "exams", "生化", "生化总题库.xlsx")

# ================= 修复：支持命令行参数传入答案文件 =================
if len(sys.argv) > 1:
    # 如果传入了参数，优先使用参数里的路径
    arg_path = sys.argv[1]
    if os.path.isabs(arg_path):
        ANSWER_PATH = arg_path
    else:
        ANSWER_PATH = os.path.join(BASE_DIR, arg_path)
else:
    # 如果没传参数，才使用默认的 00-05 路径
    ANSWER_PATH = os.path.join(BASE_DIR, "data", "exams", "生化答案", "00-05生化真题答案.xlsx")
# ====================================================================

def is_blank(v):
    return pd.isna(v) or str(v).strip() in ("", "nan", "None")


def main():
    print(f"📄 读取题目: {os.path.basename(QUESTION_PATH)}")
    qdf = pd.read_excel(QUESTION_PATH)
    # 强制转为 object 类型，允许写入字符串
    qdf["答案"] = qdf["答案"].astype(object)
    qdf["解析"] = qdf["解析"].astype(object)
    print(f"   总题数: {len(qdf)}")

    print(f"📄 读取答案: {os.path.basename(ANSWER_PATH)}")
    adf = pd.read_excel(ANSWER_PATH)
    print(f"   总答案数: {len(adf)}")

    # 构建答案字典：key = (年份, 题型, 题号)
    answer_map = {}
    for _, row in adf.iterrows():
        key = (int(row["年份"]), row["题型"], int(row["题号"]))
        answer_map[key] = {
            "答案": row["答案"],
            "解析": row["解析"] if not is_blank(row["解析"]) else "",
        }

    filled_answer = 0
    filled_explanation = 0
    matched_keys = set()

    for idx, row in qdf.iterrows():
        key = (int(row["年份"]), row["题型"], int(row["题号"]))
        if key not in answer_map:
            continue
        matched_keys.add(key)
        a = answer_map[key]

        if is_blank(row.get("答案")):
            qdf.at[idx, "答案"] = str(a["答案"])
            filled_answer += 1
        if is_blank(row.get("解析")) and a["解析"]:
            qdf.at[idx, "解析"] = str(a["解析"])
            filled_explanation += 1

    # 未匹配的答案
    unused_answers = [k for k in answer_map if k not in matched_keys]

    print(f"\n✅ 匹配完成")
    print(f"  填充答案: {filled_answer} 条")
    print(f"  填充解析: {filled_explanation} 条")
    print(f"  匹配上: {len(matched_keys)} 条")
    print(f"  未使用的答案: {len(unused_answers)} 条")

    # 按年份统计未匹配
    if unused_answers:
        year_counter = {}
        for k in unused_answers:
            year_counter[k[0]] = year_counter.get(k[0], 0) + 1
        print(f"\n📋 未匹配答案按年份：")
        for y, c in sorted(year_counter.items()):
            print(f"  {y}年: {c} 条")

    # 检查 2000-2005 年哪些题没答案（这是之前的逻辑，保留它也无妨，但可以改为由命令行控制）
    target_years = [2000, 2001, 2002, 2003, 2004, 2005]
    missing_answer_qs = qdf[
        (qdf["年份"].isin(target_years)) &
        (qdf["答案"].apply(is_blank))
    ]
    if len(missing_answer_qs) > 0:
        print(f"\n⚠️ 2000-2005 年有 {len(missing_answer_qs)} 道题没有答案：")
        print(missing_answer_qs.groupby(["年份", "题型"]).size().to_string())

    # 保存
    qdf.to_excel(QUESTION_PATH, index=False)
    print(f"\n💾 已更新: {QUESTION_PATH}")


if __name__ == "__main__":
    main()