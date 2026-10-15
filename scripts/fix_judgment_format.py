import pandas as pd
import os

# 指向需要修复的源文件
file_path = r"D:\PythonProject\deepseek_AI_project\data\exams\生化答案\00-05生化真题答案.xlsx"

print(f"正在读取 {file_path} ...")
df = pd.read_excel(file_path)

fixed_count = 0

for idx, row in df.iterrows():
    # 只处理判断题
    if str(row['题型']).strip() == '判断':
        ans = str(row['答案']).strip() if pd.notna(row['答案']) else ''
        exp = str(row['解析']).strip() if pd.notna(row['解析']) else ''

        # 判断答案是否包含粘连（以 √ 或 × 开头，且长度大于1）
        if (ans.startswith('√') or ans.startswith('×')) and len(ans) > 1:
            # 提取第一个字符作为答案
            df.at[idx, '答案'] = ans[0]
            # 剩余部分作为解析
            rest_text = ans[1:].strip()
            # 如果原有解析列不为空，则拼在一起；否则直接用剩余部分
            df.at[idx, '解析'] = (rest_text + " " + exp).strip() if exp else rest_text
            fixed_count += 1

# 保存回去，覆盖原文件
df.to_excel(file_path, index=False)
print(f"✅ 清洗完成！共修复了 {fixed_count} 条错位的判断题答案。")
print("请重新运行 merge_answers.py 将其匹配到总题库。")