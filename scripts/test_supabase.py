"""
诊断脚本：检查当前会连到哪个数据库、云端 Supabase 是否可用、库里有多少题。

用法（PyCharm Terminal，PowerShell）:
    $env:SUPABASE_HOST="db.xxxxxxxx.supabase.co"
    $env:SUPABASE_USER="postgres"
    $env:SUPABASE_PASSWORD="你的密码"
    $env:SUPABASE_DB="postgres"
    $env:SUPABASE_PORT="5432"
    .\.venv\Scripts\python.exe -u scripts\test_supabase.py
"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=== 1. 环境变量检查 ===")
for k in ["SUPABASE_HOST", "SUPABASE_USER", "SUPABASE_PASSWORD", "SUPABASE_DB", "SUPABASE_PORT"]:
    v = os.environ.get(k)
    if k == "SUPABASE_PASSWORD":
        print(f"  {k}: " + (f"已设置（长度 {len(v)}）" if v else "未设置"))
    else:
        print(f"  {k}: " + (v if v else "未设置"))

print("\n=== 2. 实际使用的数据库 ===")
from core.db import DB_URL, engine
print("  DB_URL:", DB_URL)

if not DB_URL.startswith("postgresql"):
    print("\n[X] 当前连的是本地 SQLite，没有连上 Supabase！")
    print("    说明 SUPABASE_* 环境变量没生效。常见原因：")
    print("    - 环境变量和 python 命令不在同一个终端会话里敲的")
    print("    - 终端是 cmd 而不是 PowerShell（cmd 里 $env:X= 语法无效）")
    sys.exit(0)

print("\n=== 3. 测试连接 Supabase ===")
from sqlalchemy import text

try:
    with engine.connect() as conn:
        cols = [c[0] for c in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='question'"
        )).fetchall()]
        print("  question 表字段:", cols)
        missing = [c for c in ("question_no", "answer_mode", "data_status") if c not in cols]
        print("  缺少的新字段:", missing if missing else "无（已加好）")

        n = conn.execute(text("SELECT COUNT(*) FROM question")).scalar()
        print("  question 表题数:", n)

        rows = conn.execute(text(
            "SELECT year, COUNT(*) FROM question GROUP BY year ORDER BY year"
        )).fetchall()
        print("  各年题数:", {r[0]: r[1] for r in rows})
        print("\n[OK] 连接成功！可以跑导入脚本了。")
except Exception as e:
    print("  [X] 连接失败:", repr(e))
    print("  可能原因：Supabase 项目被暂停（免费版久未使用会暂停）/ 连接信息错误 / 网络不通")
