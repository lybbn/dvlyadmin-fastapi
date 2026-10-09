# -*- coding: utf-8 -*-
"""
@Remark: 数据初始化命令（对应 Django 版: python manage.py init）
用法: python run.py init [-y|-Y|-n|-N] [模块名...]
说明：
- 默认执行 mysystem.initialize 与 apps/*/initialize.py（对齐 Django 遍历 INSTALLED_APPS 的语义）
- 指定模块名（如 mysystem、demoapp）时只执行对应模块
- -y/-Y: 种子数据先删后建；-n/-N: 保留既有直接 upsert（默认）
"""
import importlib

from application.settings import BASE_DIR
from commands.base import ok


def add_arguments(parser):
    parser.add_argument("init_name", nargs="*", type=str, help="要初始化的模块名（默认全部执行）")
    parser.add_argument("-y", nargs="*", help="先删除种子数据再重建")
    parser.add_argument("-Y", nargs="*", help="同 -y")
    parser.add_argument("-n", nargs="*", help="保留既有数据直接 upsert（默认）")
    parser.add_argument("-N", nargs="*", help="同 -n")


def _iter_initialize_modules(init_name):
    """产出要执行的 initialize 模块路径"""
    if init_name:
        for name in init_name:
            if (BASE_DIR / "apps" / name).is_dir():
                yield f"apps.{name}.initialize"
            else:
                yield f"{name}.initialize"
        return
    yield "mysystem.initialize"
    apps_dir = BASE_DIR / "apps"
    if apps_dir.is_dir():
        for app_dir in sorted(p for p in apps_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            if (app_dir / "initialize.py").exists():
                yield f"apps.{app_dir.name}.initialize"


def handle(args):
    is_delete = False
    if isinstance(args.y, list) or isinstance(args.Y, list):
        is_delete = True
    if isinstance(args.n, list) or isinstance(args.N, list):
        is_delete = False
    ok(f"正在准备初始化数据，{'如有初始化数据，将会不做操作跳过' if not is_delete else '初始数据将会先删除后新增'}...")

    for module_path in _iter_initialize_modules(args.init_name):
        try:
            module = importlib.import_module(module_path)
            module.main(is_delete=is_delete)
        except ModuleNotFoundError:
            pass
    ok("初始化数据完成！")
    return 0