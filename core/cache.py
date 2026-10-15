import streamlit as st
from core.models import Question, active_q_filter


@st.cache_data(ttl=60)
def get_chapters_cached(_session):
    return sorted([
        r[0] for r in
        _session.query(Question.chapter_name).filter(active_q_filter()).distinct().all()
        if r[0]
    ])


@st.cache_data(ttl=30)
def get_wrong_count_cached(_session):
    from core.models import StudyEvent
    active_ids = set(
        r[0] for r in _session.query(Question.id).filter(active_q_filter()).all()
    )
    return len(set(
        r[0] for r in
        _session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question",
                StudyEvent.is_correct == False)
        .distinct().all()
    ) & active_ids)
