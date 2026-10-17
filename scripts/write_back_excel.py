# -*- coding: utf-8 -*-
"""把数据库里的章节/考点写回 Excel 的「章节」「考点」两列。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from core.db import get_session
from core.models import Question

EXCEL = os.path.join("data", "exams", "生化", "生化总题库.xlsx")


def main():
    if os.path.exists(f"~${os.path.basename(EXCEL)}") or os.path.exists(
            os.path.join(os.path.dirname(EXCEL), f"~${os.path.basename(EXCEL)}")):
        print("⚠️ 检测到 Excel 锁文件，请先关闭 Excel/WPS 再运行")
        sys.exit(1)

    session = get_session()
    q_map = {}
    for q in session.query(Question).all():
        stem = (q.stem or "").strip()
        ch = q.chapter_name or ""
        kp = q.kp_text or ""
        if not kp:
            # 兜底：用章节名
            kp = (ch or "").replace("第", "").replace("章", "").strip()
        q_map[(q.year, stem)] = (ch, kp)

    df = pd.read_excel(EXCEL)
    print(f"Excel 行数: {len(df)}")
    # 全空列被 pandas 读成 float64，先转 object 才能写字符串
    df["章节"] = df["章节"].astype("object")
    df["考点"] = df["考点"].astype("object")

    matched = 0
    for i, row in df.iterrows():
        year = row.get("年份")
        stem = row.get("题干")
        if pd.isna(stem):
            continue
        key = (year, str(stem).strip())
        if key in q_map:
            ch, kp = q_map[key]
            df.at[i, "章节"] = ch
            df.at[i, "考点"] = kp
            matched += 1

    print(f"匹配写回: {matched} / {len(df)}")

    df.to_excel(EXCEL, index=False)
    print("✅ 已写回 Excel:", EXCEL)


if __name__ == "__main__":
    main()
