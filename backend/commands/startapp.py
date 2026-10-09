# -*- coding: utf-8 -*-
"""
@Remark: 创建新业务模块命令（对应 Django 版: python manage.py lystartapp app名）
用法: python run.py startapp app名 [app名2 ...]（lystartapp 为兼容别名）
说明：在 apps/ 目录生成模块骨架（__init__/models/views/urls/schemas/initialize），
      不生成 migrations/apps.py（SQLAlchemy 无需），路由按 urls.py 注释手工接入
"""
import keyword

from application.settings import BASE_DIR
from commands.base import err, ok


def add_arguments(parser):
    parser.add_argument("appname", nargs="*", type=str, help="模块名（可多个）")


def _models_tpl(name):
    return f'''# -*- coding: utf-8 -*-

"""
@Remark: {name} 数据模型
说明：本框架表结构约定 —— 表名以 lyadmin_ 前缀；本模块模型由 python run.py db_init 建表
"""

from application.database import Base
from utils.models import CoreModelMixin, BaseModelMixin  # noqa: F401
'''


def _schemas_tpl(name):
    return f'''# -*- coding: utf-8 -*-

"""
@Remark: {name} Pydantic 模型
"""

from pydantic import BaseModel  # noqa: F401
'''


def _views_tpl(name):
    return f'''# -*- coding: utf-8 -*-

"""
@Remark: {name} 业务视图
接入方式：在 application/urls.py 中 include_router（参考 mysystem 的注册方式）
"""

from fastapi import APIRouter

router = APIRouter()
'''


def _urls_tpl(name):
    return f'''# -*- coding: utf-8 -*-

"""
@Remark: {name} 路由文件
接入方式（application/urls.py）:
    from apps.{name}.urls import router as {name}_router
    api_router.include_router({name}_router, prefix="/api/{name}")
"""

from fastapi import APIRouter

router = APIRouter()
'''


def _initialize_tpl(name):
    return f'''# -*- coding: utf-8 -*-

"""
@Remark: {name} 初始化数据（python run.py init 时自动执行）
"""


def main(is_delete=False):
    """
    初始化 {name} 数据
    :param is_delete: True 时先删除种子数据再重建（python run.py init -y）
    """
    pass
'''


def handle(args):
    names = args.appname
    if not names:
        ok("提示：该命令会把模块创建到 apps 目录中")
        ok("请输入要创建的模块名称如：python run.py startapp app名")
        return 0

    apps_dir = BASE_DIR / "apps"
    for name in names:
        if not name.isidentifier() or keyword.iskeyword(name):
            err(f"App名称：{name} 不是合法的Python模块名，请更换其他名称！")
            continue
        app_path = apps_dir / name
        if app_path.exists():
            ok(f"要创建的App名称：{name} 已存在，请更换其他名称！")
            continue

        app_path.mkdir(parents=True)
        if not (apps_dir / "__init__.py").exists():
            (apps_dir / "__init__.py").write_text("", encoding="UTF-8")
        files = {
            "__init__.py": "",
            "models.py": _models_tpl(name),
            "schemas.py": _schemas_tpl(name),
            "views.py": _views_tpl(name),
            "urls.py": _urls_tpl(name),
            "initialize.py": _initialize_tpl(name),
        }
        for filename, content in files.items():
            (app_path / filename).write_text(content, encoding="UTF-8")

        ok(f"App名称：{name} 创建成功！")
    return 0