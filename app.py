import streamlit as st

st.set_page_config(page_title="考研专业课复习", page_icon="📚", layout="wide")

st.title("📚 考研专业课复习系统")
st.markdown("""
### 欢迎

左侧选择页面：

- 📖 **刷题**：核心功能（出题 → 自评 → 看答案 → 校准）
- 📕 **错题本**（待开发）
- 📊 **总结**（待开发）
- ⚙️ **设置**（待开发）

---
**当前版本 v0.1** · 数据源：现代生物化学真题
""")