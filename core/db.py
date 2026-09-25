import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True)


def _read_supabase_config():
    """优先从 Streamlit Secrets 读；其次从环境变量读；都没有则返回 None"""
    host = user = password = None
    dbname = "postgres"
    port = 5432

    # 1) 尝试 Streamlit Secrets（部署在 Cloud 时）
    try:
        import streamlit as st
        if "supabase" in st.secrets:
            sec = st.secrets["supabase"]
            host = sec.get("host")
            user = sec.get("user")
            password = sec.get("password")
            dbname = sec.get("dbname", "postgres")
            port = int(sec.get("port", 5432))
    except Exception:
        pass

    # 2) 环境变量兜底（本地测试用）
    if not host:
        host = os.environ.get("SUPABASE_HOST")
        user = os.environ.get("SUPABASE_USER")
        password = os.environ.get("SUPABASE_PASSWORD")
        dbname = os.environ.get("SUPABASE_DB", "postgres")
        port = int(os.environ.get("SUPABASE_PORT", "5432"))

    if host and user and password:
        return {
            "host": host, "user": user, "password": password,
            "dbname": dbname, "port": port,
        }
    return None


def _build_db_url():
    cfg = _read_supabase_config()
    if cfg:
        # quote_plus 会自动把 ^ 编码成 %5E，@ 编码成 %40 等
        pwd_enc = quote_plus(cfg["password"])
        return (
            f"postgresql+psycopg2://{cfg['user']}:{pwd_enc}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
        )
    # 默认本地 SQLite
    db_path = os.path.join(DB_DIR, "kaoyan.db")
    return f"sqlite:///{db_path}"


DB_URL = _build_db_url()

# 打印一下用的是哪个数据库（启动时看得到）
if DB_URL.startswith("postgresql"):
    print("🗄️ 数据库：Supabase (PostgreSQL)")
else:
    print(f"🗄️ 数据库：本地 SQLite -> {DB_URL}")

# 向后兼容：旧代码里引用的 DB_PATH
DB_PATH = DB_URL

engine = create_engine(DB_URL, echo=False, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def get_session():
    return SessionLocal()