import os
import re
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import get_session
from core.models import Question, KnowledgePoint, QuestionKP, ReviewItem

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(BASE_DIR, "data", "output", "parsed_questions.json")


def split_kps(text):
    if not text:
        return []
    parts = re.split(r"[、,，;；]+", text)
    return [p.strip() for p in parts if p.strip()]


def main():
    if not os.path.exists(JSON_PATH):
        print(f"❌ 找不到 {JSON_PATH}")
        return
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)
    print(f"📄 读取 {len(questions)} 道题目")

    session = get_session()

    # 清空旧数据
    session.query(QuestionKP).delete(synchronize_session=False)
    session.query(KnowledgePoint).delete(synchronize_session=False)
    session.query(ReviewItem).filter(ReviewItem.item_type == "question").delete(synchronize_session=False)
    session.query(Question).delete(synchronize_session=False)
    session.commit()

    kp_cache = {}
    chapter_set = set()

    for q in questions:
        question = Question(
            type="简答",
            stem=q["stem"],
            answer=q["answer"],
            source=f"{q['year']}年",
            year=q["year"],
            kp_text=q["kp_text"],
            chapter_name=q.get("chapter") or "未分类",   # ← 写入章节
            book="现代生物化学",
        )
        session.add(question)
        session.flush()
        chapter_set.add(question.chapter_name)

        for kp_name in split_kps(q["kp_text"]):
            if kp_name not in kp_cache:
                kp = session.query(KnowledgePoint).filter(KnowledgePoint.name == kp_name).first()
                if kp is None:
                    kp = KnowledgePoint(name=kp_name, importance=3)
                    session.add(kp)
                    session.flush()
                kp_cache[kp_name] = kp.id
            session.add(QuestionKP(question_id=question.id, kp_id=kp_cache[kp_name]))

        session.add(ReviewItem(item_type="question", item_id=question.id))

    session.commit()

    q_count = session.query(Question).count()
    kp_count = session.query(KnowledgePoint).count()
    ri_count = session.query(ReviewItem).filter(ReviewItem.item_type == "question").count()
    print(f"✅ 入库完成: {q_count} 道题 / {kp_count} 个知识点 / {ri_count} 个复习项")
    print(f"\n📚 章节数: {len(chapter_set)}")
    for c in sorted(chapter_set):
        print(f"  - {c}")
    session.close()


if __name__ == "__main__":
    main()