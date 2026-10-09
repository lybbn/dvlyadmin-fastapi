# -*- coding: utf-8 -*-
"""
@Remark: FastAPI 版配置聚合（对应 Django application/settings.py）
职责：
(1) 聚合 config.py 的环境配置
(2) 拼装 SQLAlchemy 数据库连接串
(3) SIMPLE_JWT / 限速 / 目录 / 日志 等全局配置
注意：SECRET_KEY 必须与 Django 后端一致（同一环境变量或同一默认值），
这是 JWT 与 Django simplejwt 完全互通的前提。
"""
import logging
import os
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote_plus

from config import *  # noqa: F401,F403  与 Django 版保持一致的配置引入方式

BASE_DIR = Path(__file__).resolve().parent.parent

# ================================================= #
# ************** 安全密钥（JWT 互通关键） ************** #
# ================================================= #
# 与 Django 后端使用同一环境变量 DJANGO_SECRET_KEY；未设置时回退到与
# Django 版相同的默认值，保证 FastAPI 签发/校验的 JWT 与 simplejwt 完全互通
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or \
    'django-insecure-+9y7-(76!+viys!c(lybbn24s3h&-zm&l#fujgn03*+-yj@4'

# ================================================= #
# ************** 数据库连接串 ************** #
# ================================================= #

def _build_database_url() -> str:
    """按 DATABASE_TYPE 拼装 SQLAlchemy 连接串（对齐 Django DATABASES 配置分支）"""
    if DATABASE_TYPE == "MYSQL":
        return (
            f"mysql+pymysql://{quote_plus(str(DATABASE_USER))}:{quote_plus(str(DATABASE_PASSWORD))}"
            f"@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}?charset=utf8mb4"
        )
    if DATABASE_TYPE == "POSTGRESQL":
        return (
            f"postgresql+psycopg2://{quote_plus(str(DATABASE_USER))}:{quote_plus(str(DATABASE_PASSWORD))}"
            f"@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
        )
    # SQLITE3：使用本项目自己的 db.sqlite3（与 Django 完全独立，
    # 初始库从 backend/db.sqlite3 复制而来，之后两端数据各自演化互不影响）
    return f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"


SQLALCHEMY_DATABASE_URL = _build_database_url()

# Django 侧 CONN_MAX_AGE=0（短连接），这里用探活+回收的连接池取得等价的健壮性
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,   # 取连接前探活，防止 MySQL 八小时断连报错
    "pool_recycle": 3600,
    "pool_size": 10,
    "max_overflow": 20,
}

# ================================================= #
# ************** simplejwt 对齐配置 ************** #
# ================================================= #
# 与 backend/application/settings.py 的 SIMPLE_JWT 保持一致
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),    # token有效时长
    "REFRESH_TOKEN_LIFETIME": timedelta(days=2),   # token刷新后的有效时间
    "AUTH_HEADER_TYPES": ("JWT",),                 # Authorization 头前缀：JWT <token>
    "ROTATE_REFRESH_TOKENS": True,
    "ALGORITHM": "HS256",                          # 与 simplejwt 默认一致
}

# ================================================= #
# ************** 接口限速（对齐 DRF 节流配置） ************** #
# ================================================= #
THROTTLE_RATES = {
    "anon": "60/minute",    # 未登录用户每分钟可以请求60次
    "user": "160/minute",   # 已登录用户每分钟可以请求160次
}

# ================================================= #
# ************** 日志/节流（阶段5） ************** #
# ================================================= #
# 对齐 Django API_LOG_ENABLE/API_LOG_METHODS：'UPDATE' 非 HTTP 方法恒不匹配 → 实际只记 POST/PUT/DELETE
API_LOG_ENABLE = True
API_LOG_METHODS = ['POST', 'UPDATE', 'DELETE', 'PUT']
# 日志记录显示的请求模块中文名映射（对齐 Django API_MODEL_MAP）
API_MODEL_MAP = {
    "/api/token/": "登录模块",
    "/api/token/refresh/": "登录刷新",
    "/api/super/operate/": "前端API关闭开启",
    "/api/system/sys_image_upload/": "图片上传"
}
# ViewSet.register 时自动登记 {资源前缀: model}（日志中间件 req_modular 回退用）
API_VIEW_MODEL_MAP = {}
# THROTTLE_RATES 见上方（对齐 DRF DEFAULT_THROTTLE_RATES：anon 60/minute + user 160/minute）

# ================================================= #
# ************** 目录路径 ************** #
# ================================================= #
# 静态/媒体资产使用 FastAPI 版自己的目录（与 Django 解耦）：
# - STATIC_ROOT：从 backend/static 同步的 collectstatic 产物（favicon/index.html/rest_framework 等）
# - MEDIA_ROOT：上传文件独立存储，双跑各自写入互不影响
# - FRONTEND_ROOT：集成部署的 lyadmin/h5 页面目录（当前为空，两端共用 backend/frontend）
FRONTEND_ROOT = BASE_DIR.parent / "backend" / "frontend"  # 集成部署的 lyadmin/h5 页面目录
STATIC_ROOT = BASE_DIR / "static"                          # 本项目自有静态目录（已从 Django 同步）
STATIC_URL = "/static/"
MEDIA_ROOT = BASE_DIR / "media"                            # 本项目自有上传文件根目录
MEDIA_URL = "/media/"
LOGS_DIR = BASE_DIR / "logs"

# ================================================= #
# ************** 日志配置（对齐 Django LOGGING） ************** #
# ================================================= #
# 格式:[日期][模块.函数名称():行号] [级别] 信息
STANDARD_LOG_FORMAT = '[%(asctime)s][%(name)s.%(funcName)s():%(lineno)d] [%(levelname)s] %(message)s'


def setup_logging():
    """初始化与 Django 版一致的日志体系：控制台 + logs/server.log + logs/error.log"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if getattr(root, "_dvlyadmin_fastapi_logging_ready", False):
        return  # uvicorn 多进程/reload 下避免重复挂 handler
    root.setLevel(logging.INFO)

    standard_fmt = logging.Formatter(STANDARD_LOG_FORMAT)
    console_fmt = logging.Formatter(STANDARD_LOG_FORMAT, datefmt='%Y-%m-%d %H:%M:%S')

    file_handler = RotatingFileHandler(
        LOGS_DIR / 'server.log',
        maxBytes=1024 * 1024 * 20,  # 20 MB
        backupCount=10,             # 最多备份10个
        encoding='utf-8',
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(standard_fmt)

    error_handler = RotatingFileHandler(
        LOGS_DIR / 'error.log',
        maxBytes=1024 * 1024 * 20,
        backupCount=10,
        encoding='utf-8',
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(standard_fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)

    root.addHandler(file_handler)
    root.addHandler(error_handler)
    root.addHandler(console_handler)
    root._dvlyadmin_fastapi_logging_ready = True
