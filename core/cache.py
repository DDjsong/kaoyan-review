import streamlit as st


@st.cache_data(ttl=60)
def get_chapters_cached(_session):
    from core.models import Question
    return sorted([r[0] for r in _session.query(Question.chapter_name).distinct().all() if r[0]])


@st.cache_data(ttl=30)
def get_wrong_count_cached(_session):
    from core.models import StudyEvent
    return len(set(
        r[0] for r in
        _session.query(StudyEvent.item_id)
        .filter(StudyEvent.item_type == "question",
                StudyEvent.is_correct == False)
        .distinct().all()
    ))