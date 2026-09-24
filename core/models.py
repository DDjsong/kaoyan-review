from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey
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
    stem = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    source = Column(String(200), nullable=True)
    year = Column(Integer, nullable=True)
    kp_text = Column(Text, nullable=True)
    chapter_name = Column(String(200), nullable=True)   # ← 新增
    chapter_id = Column(Integer, ForeignKey("chapter.id"), nullable=True)
    book = Column(String(100), nullable=True)


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