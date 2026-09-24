import os
import sys

# 让脚本能找到 core 包
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import engine, DB_PATH
from core.models import Base
from sqlalchemy import inspect


def init_db():
    print(f"📁 数据库路径: {DB_PATH}")
    Base.metadata.create_all(engine)
    print("✅ 建表完成")

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("\n📋 已创建的表:")
    for t in tables:
        print(f"  - {t}")


if __name__ == "__main__":
    init_db()