from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, func
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Chapter(Base):
    __tablename__ = "chapter"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("chapter.id"), nullable=True)
    order = Column(Integer, default=0)
    book = Column(String(100), nullable=True)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_point"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(300), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapter.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("knowledge_point.id"), nullable=True)
    importance = Column(Integer, default=3)
    summary = Column(Text, nullable=True)
    source_ref = Column(String(200), nullable=True)


class Question(Base):
    __tablename__ = "question"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(20), default="简答")
    question_type = Column(String(20), nullable=True)     # 判断/选择/填空/名词解释/问答
    stem = Column(Text, nullable=False)
    options = Column(Text, nullable=True)                 # JSON: {"A": "...", "B": "..."}
    blanks = Column(Text, nullable=True)                  # JSON: ["答案1", "答案2"]
    answer = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    source = Column(String(200), nullable=True)
    year = Column(Integer, nullable=True)
    kp_text = Column(Text, nullable=True)
    chapter_name = Column(String(200), nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapter.id"), nullable=True)
    book = Column(String(100), nullable=True)
    question_no = Column(Integer, nullable=True)      # 题号
    answer_mode = Column(String(20), nullable=True)   # choice/input/self
    data_status = Column(String(20), default="正常")  # 正常/存疑/停用


class QuestionKP(Base):
    __tablename__ = "question_kp"
    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("question.id"), nullable=False)
    kp_id = Column(Integer, ForeignKey("knowledge_point.id"), nullable=False)


class StudyEvent(Base):
    __tablename__ = "study_event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String(20), nullable=False)
    item_id = Column(Integer, nullable=False)
    self_rating = Column(String(20), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    error_type = Column(String(30), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class ReviewItem(Base):
    __tablename__ = "review_item"
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String(20), nullable=False)
    item_id = Column(Integer, nullable=False)
    due = Column(DateTime, default=datetime.now)
    interval = Column(Integer, default=0)
    ease = Column(Float, default=2.5)
    reps = Column(Integer, default=0)
    state = Column(String(20), default="learning")

class AIAdvice(Base):
    __tablename__ = "ai_advice"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now)
    advice_json = Column(Text, nullable=True)
    stats_snapshot = Column(Text, nullable=True)


# ========================================================
# 公共查询过滤条件
# ========================================================

def active_q_filter():
    """只保留「未停用」的题目。

    - data_status = '停用' 的题（如暂无答案的 2026 年题）不参与抽题/统计。
    - 用 coalesce 兜底：data_status 为 NULL 的老数据视作「正常」，
      否则 SQL 里 `NULL != '停用'` 结果为 NULL，会把老题误排除。
    """
    return func.coalesce(Question.data_status, "正常") != "停用"


def is_doubtful(q):
    """判断题是否为「存疑」状态（答案待核对）。"""
    return (getattr(q, "data_status", None) or "正常") == "存疑"
