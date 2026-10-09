# -*- coding: utf-8 -*-
"""
@Remark: SQLAlchemy 引擎与会话管理（对应 Django 的数据库连接层）
重要约定：只映射既有表结构（lyadmin_*），本层绝不建表/改表——
表结构由 Django 迁移体系管理；独立开发（不依赖 Django）时由
`python run.py db_init` 命令建表（本项目唯一允许建表的入口）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from application import settings


class Base(DeclarativeBase):
    """全部 ORM 模型的声明基类"""


_engine_kwargs = dict(settings.SQLALCHEMY_ENGINE_OPTIONS)
if settings.DATABASE_TYPE == "SQLITE3":
    # sqlite 文件库不支持 pool_size/max_overflow 连接池参数
    _engine_kwargs = {"pool_pre_ping": True}

engine = create_engine(settings.SQLALCHEMY_DATABASE_URL, **_engine_kwargs)

# expire_on_commit=False：commit 后仍可访问对象属性，贴近 Django ORM 的使用习惯
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖注入用的数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
