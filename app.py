import streamlit as st

st.set_page_config(
    page_title="考研专业课复习系统",
    page_icon="📚",
    layout="wide",
)

# ============== 自定义样式 ==============
st.markdown("""
<style>
/* 隐藏 Streamlit 默认的页脚和菜单 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

/* 主容器渐变背景 */
.stApp {
    background: linear-gradient(135deg, #eef2ff 0%, #e0f2fe 50%, #f0fdf4 100%);
    background-attachment: fixed;
}

/* 主标题 */
.hero-title {
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(90deg, #4A90E2 0%, #10B981 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-align: center;
    margin-bottom: 0.5rem;
    padding-top: 2rem;
}

.hero-subtitle {
    text-align: center;
    font-size: 1.15rem;
    color: #64748b;
    margin-bottom: 3rem;
}

/* 功能卡片 */
.feature-card {
    background: rgba(255, 255, 255, 0.85);
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 4px 20px rgba(74, 144, 226, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.9);
    height: 100%;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.feature-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 30px rgba(74, 144, 226, 0.15);
}

.feature-icon {
    font-size: 2.2rem;
    margin-bottom: 0.5rem;
}

.feature-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #1e293b;
    margin-bottom: 0.5rem;
}

.feature-desc {
    color: #64748b;
    font-size: 0.92rem;
    line-height: 1.6;
}

/* 底部提示 */
.footer-note {
    text-align: center;
    color: #94a3b8;
    font-size: 0.85rem;
    margin-top: 3rem;
    padding-bottom: 2rem;
}

/* 侧栏样式 */
section[data-testid="stSidebar"] {
    background: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(10px);
}
</style>
""", unsafe_allow_html=True)

# ============== 页面内容 ==============
st.markdown('<div class="hero-title">📚 考研专业课复习系统</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-subtitle">主动回忆 · 间隔重复 · AI 辅助 · 让背诵更高效</div>',
    unsafe_allow_html=True,
)

# 四张卡片
col1, col2, col3, col4 = st.columns(4, gap="medium")

with col1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">📖</div>
        <div class="feature-title">刷题</div>
        <div class="feature-desc">
            按范围出题：全部 / 指定章节 / 错题本。<br>
            自评 → 看答案 → 校准 → 选错因。
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">📕</div>
        <div class="feature-title">错题本</div>
        <div class="feature-desc">
            自动记录错题，按知识点聚合。<br>
            按遗忘曲线安排复习。
        </div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">📊</div>
        <div class="feature-title">总结</div>
        <div class="feature-desc">
            学习统计、自评分布、错因分析、<br>
            薄弱知识点、章节掌握度。
        </div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🤖</div>
        <div class="feature-title">AI 老师</div>
        <div class="feature-desc">
            错因诊断 · 知识点精讲<br>
            记忆技巧 · 相近题推荐
        </div>
    </div>
    """, unsafe_allow_html=True)

# 底部提示
st.markdown("---")
st.markdown("""
<div class="footer-note">
    👈 从左侧选择页面开始使用
    <br><br>
    v0.1 · 数据源：现代生物化学真题
</div>
""", unsafe_allow_html=True)