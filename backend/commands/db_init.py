# -*- coding: utf-8 -*-
"""
@Remark: 数据库建表命令（FastAPI 独立化：承载 Django migrations 的建表职责）
用法: python run.py db_init
说明：
- 对空库：按模型定义创建全部表（lyadmin_* + captcha_captchastore）
- 对既有库（如从 Django 复制的 db.sqlite3）：checkfirst 逐表判断，不重建、不改表、不丢数据
- 本项目唯一允许建表的入口（数据库层的"只映射不建表"约定仅在此命令下例外）
"""
import importlib

from sqlalchemy import inspect

from application.database import Base, engine
from application.settings import BASE_DIR
from commands.base import ok


def add_arguments(parser):
    """db_init 无参数"""


def _load_all_models():
    """确保 Base.metadata 完整：显式加载 mysystem 模型 + 自动发现 apps/*/models.py"""
    import mysystem.models  # noqa: F401

    apps_dir = BASE_DIR / "apps"
    if not apps_dir.is_dir():
        return
    for app_dir in sorted(p for p in apps_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        if (app_dir / "models.py").exists():
            importlib.import_module(f"apps.{app_dir.name}.models")


def handle(args):
    _load_all_models()

    before = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine, checkfirst=True)
    after = set(inspect(engine).get_table_names())

    created = sorted(after - before)
    if created:
        ok(f"建表完成，本次新建 {len(created)} 张表：")
        for name in created:
            ok(f"  + {name}")
    else:
        ok(f"所有表已存在（共 {len(after)} 张），未做任何变更。")
    return 0