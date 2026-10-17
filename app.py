import streamlit as st

from core import pages_impl

st.set_page_config(
    page_title="考研专业课复习系统",
    page_icon="📚",
    layout="wide",
)

# ============== 自定义样式（全局注入，必须在 st.navigation 之前） ==============
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


# ============== 构建页面 ==============
# 同一个函数文件/闭包不能重复指向（duplicate page 报错），
# 这里每个「科目-页面」都是一个独立闭包实例，并分配唯一的 url_path。

def _mk(fn, subject):
    def _page():
        fn(subject)
    return _page


biochem_study = st.Page(
    _mk(pages_impl.study_page, "生化"), title="学习", icon="📖", url_path="study_biochem")
biochem_wrong = st.Page(
    _mk(pages_impl.wrong_page, "生化"), title="错题本", icon="📕", url_path="wrong_biochem")
biochem_summary = st.Page(
    _mk(pages_impl.summary_page, "生化"), title="总结", icon="📊", url_path="summary_biochem")

cell_study = st.Page(
    _mk(pages_impl.study_page, "细胞"), title="学习", icon="📖", url_path="study_cell")
cell_wrong = st.Page(
    _mk(pages_impl.wrong_page, "细胞"), title="错题本", icon="📕", url_path="wrong_cell")
cell_summary = st.Page(
    _mk(pages_impl.summary_page, "细胞"), title="总结", icon="📊", url_path="summary_cell")

# 注册「科目 -> 学习页 Page」，供错题本「立刻重做」用 st.switch_page(Page) 跳转
pages_impl.register_study_pages({
    "生化": biochem_study,
    "细胞": cell_study,
})

pages = {
    "": [
        st.Page(pages_impl.home_page, title="首页", icon="🏠", default=True),
    ],
    "生化": [biochem_study, biochem_wrong, biochem_summary],
    "细胞": [cell_study, cell_wrong, cell_summary],
    "AI 老师": [st.Page(pages_impl.ai_page, title="AI 老师", icon="🤖", url_path="ai")],
    "设置": [st.Page(pages_impl.settings_page, title="设置", icon="⚙️", url_path="settings")],
}

pg = st.navigation(pages)
pg.run()
