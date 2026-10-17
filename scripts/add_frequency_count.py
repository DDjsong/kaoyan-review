# -*- coding: utf-8 -*-
"""给 kp_frequency 补充「出现次数」：高频 · 出现27次（标签 + 次数都要）。"""
import os
import sys
import io
import re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question


def main():
    session = get_session()
    qs = session.query(Question).all()

    # 统计每个知识点（kp_text 第一个）出现次数（按 subject 分开）
    first_kp = {}
    for q in qs:
        kp = (q.kp_text or "").strip()
        if kp:
            first = re.split(r"[、，；;,/]", kp)[0].strip()
            first_kp[q.id] = (first, q.subject)
    counter = Counter(v for v in first_kp.values())

    n = 0
    for q in qs:
        if q.id not in first_kp:
            continue
        first, subject = first_kp[q.id]
        cnt = counter[(first, subject)]
        tag = (q.kp_frequency or "").strip()
        if tag and "出现" not in tag:
            q.kp_frequency = f"{tag} · 出现{cnt}次"
            n += 1
    session.commit()
    print(f"✅ 更新 {n} 道题的考频（标签 + 次数）")
    # 样例
    for q in session.query(Question).filter(Question.kp_frequency.like("%出现%")).limit(5).all():
        print(f"  [{q.subject}] {q.kp_text[:20]} -> {q.kp_frequency}")


if __name__ == "__main__":
    main()
