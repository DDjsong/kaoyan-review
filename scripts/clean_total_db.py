import pandas as pd
import os
import re

file_path = r"D:\PythonProject\deepseek_AI_project\data\exams\生化\生化总题库.xlsx"

print(f"正在读取 {file_path} ...")
df = pd.read_excel(file_path)

# 去除列名可能存在的隐藏空格
df.columns = df.columns.str.strip()

# 定义所有可能的对错符号
true_symbols = ['√', '✓', '✔', 'v', 'V']
false_symbols = ['×', 'x', 'X', '✗', '✘']
all_symbols = true_symbols + false_symbols

fixed_count = 0

print("--- 开始清洗错位的判断题答案 ---")
for idx, row in df.iterrows():
    if str(row.get('题型', '')).strip() == '判断':
        # 安全提取，并强制转为字符串
        ans = str(row.get('答案', '')).strip() if pd.notna(row.get('答案')) else ''
        exp = str(row.get('解析', '')).strip() if pd.notna(row.get('解析')) else ''

        # 1. 清除WPS或Excel自动添加的隐藏前导单引号（关键修复！）
        if ans.startswith("'"):
            ans = ans[1:].strip()

        if len(ans) > 1:
            # 2. 利用正则表达式在前3个字符中寻找对错符号
            # 这样可以容忍 "√", " √", "√ " 等各种情况
            match = re.search(r'([√✓✔×xX✗✘vV])', ans[:3])
            if match:
                sym_idx = match.start(1)
                # 只有符号在字符中间时才进行拆分（例如 √xxxx）
                if sym_idx < len(ans) - 1:
                    df.at[idx, '答案'] = ans[sym_idx]
                    rest_text = ans[sym_idx + 1:].strip()
                    # 合并到解析列
                    df.at[idx, '解析'] = (rest_text + " " + exp).strip() if exp else rest_text
                    fixed_count += 1
                    # 打印前5条修复记录，供你检查
                    if fixed_count <= 5:
                        print(
                            f"修复行 {idx} ({row['年份']} {row['题号']}): [{ans}] -> 答案: [{ans[sym_idx]}], 解析: [{df.at[idx, '解析']}]")

if fixed_count > 0:
    df.to_excel(file_path, index=False)
    print(f"\n✅ 清洗完成！共修复了 {fixed_count} 条错位的判断题答案。")
    print("请打开总题库，筛选 2007 和 2009 年判断题，确认答案和解析是否已分开。")
else:
    print("\n⚠️ 未发现错位需要修复的数据。请检查上方打印的调试信息。")