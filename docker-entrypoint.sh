#!/bin/sh
# ========================================================= #
# dvlyadmin-fastapi Docker 容器启动脚本
# 流程：持久化目录初始化 -> 等待 MySQL 就绪（Python 探测） -> db_init 建表 -> 初始化数据 -> 启动 uvicorn
# 说明：FastAPI 版无 Django migrate，建表职责由 db_init 承载（checkfirst 幂等，可重复执行）
# ========================================================= #
set -e

echo "==> [dvlyadmin-fastapi] 启动入口脚本"

# ---------------- 持久化目录初始化 ----------------
# 软链接已在 Dockerfile 构建时创建；此处仅确保挂载卷的子目录存在
mkdir -p /app/backend/data/media /app/backend/data/logs

# ---------------- 等待 MySQL 就绪（纯 Python 探测，无需 mysql-client） ----------------
MAX_WAIT=120
WAITED=0
until python -c "
import os, sys
import pymysql
try:
    pymysql.connect(
        host=os.environ.get('DVLYADMIN_DATABASE_HOST', 'mysql'),
        port=int(os.environ.get('DVLYADMIN_DATABASE_PORT', '3306')),
        user=os.environ.get('DVLYADMIN_DATABASE_USER', 'root'),
        password=os.environ.get('DVLYADMIN_DATABASE_PASSWORD', 'root'),
        connect_timeout=3,
    ).close()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "    [错误] 等待 MySQL 超时（${MAX_WAIT}s），退出。"
        exit 1
    fi
    echo "    等待 MySQL 就绪... (${WAITED}s)"
    sleep 2
done
echo "==> [dvlyadmin-fastapi] MySQL 已就绪"

# ---------------- 执行数据库建表（幂等） ----------------
echo "==> [dvlyadmin-fastapi] 执行 db_init 建表（checkfirst，已有表不受影响）"
python manage.py db_init

# ---------------- 初始化数据（仅首次） ----------------
# 通过标记文件避免重复初始化，标记文件放在挂载卷内，容器重建不丢失
INIT_FLAG="/app/backend/data/.initialized"
RUN_INIT="${DVLYADMIN_RUN_INIT:-true}"
if [ "$RUN_INIT" = "true" ] && [ ! -f "$INIT_FLAG" ]; then
    echo "==> [dvlyadmin-fastapi] 执行 init 初始化数据"
    python manage.py init && touch "$INIT_FLAG" || echo "    [警告] init 执行失败，可手动执行 python manage.py init"
else
    echo "==> [dvlyadmin-fastapi] 跳过初始化（已初始化或 RUN_INIT!=true）"
fi

# ---------------- 启动应用 ----------------
echo "==> [dvlyadmin-fastapi] 启动应用：$@"
exec "$@"
