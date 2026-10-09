# -*- coding: utf-8 -*-
"""
@Remark: 公共基础 model 混入（对应 Django utils/models.py 的 CoreModel/BaseModel）
重要约定（与 Django 既有表结构一一对应）：
(1) 全部业务表以 lyadmin_ 为前缀（table_prefix）
(2) 主键 id 为 32 位 uuid hex 字符串（varchar(100)）
(3) Django 的 ForeignKey(db_constraint=False) 落库列名为 <字段>_id，且数据库中
    没有真实外键约束，因此本层一律用普通字符串列表达关联（如 creator_id），
    不建 SQLAlchemy ForeignKey，保证与现有库结构零差异
(4) 时间字段为本地无时区时间（对齐 Django USE_TZ=False + TIME_ZONE=Asia/Shanghai）
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.orm import declarative_mixin

table_prefix = "lyadmin_"  # 数据库表名前缀


def make_uuid():
    # .hex 将生成的uuid字符串中的 - 删除，带-是36位字符，不带-是32位随机字符串
    return uuid.uuid4().hex


@declarative_mixin
class CoreModelMixin:
    """核心标准字段混入：审计字段齐全（对应 Django CoreModel 抽象基类）"""

    id = Column(String(100), primary_key=True, default=make_uuid, comment="Id")
    # Django CoreModel.creator 为 FK(db_constraint=False)，落库列名 creator_id
    creator_id = Column(String(100), nullable=True, comment="创建人")
    modifier = Column(String(100), nullable=True, comment="修改人")
    dept_belong = Column(String(100), nullable=True, comment="数据归属部门")
    # auto_now / auto_now_add 分别对应 onupdate / default
    update_datetime = Column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now, comment="修改时间")
    create_datetime = Column(DateTime, nullable=True, default=datetime.now, comment="创建时间")


@declarative_mixin
class BaseModelMixin:
    """基本字段混入（对应 Django BaseModel 抽象基类）"""

    update_datetime = Column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    create_datetime = Column(DateTime, nullable=True, default=datetime.now, comment="创建时间")
    is_delete = Column(Boolean, default=False, comment="是否逻辑删除")


# ================================================= #
# ************** 模型自省（对应 Django get_project_app_models / get_all_models_objects） ************** #
# ================================================= #

# 模型 verbose_name（对齐 Django mysystem/models.py Meta.verbose_name，菜单列/配置模块用到）
_MODEL_VERBOSE_NAMES = {
    "Users": "用户表",
    "Role": "角色表",
    "RoleMenuPermission": "角色菜单权限表",
    "RoleMenuButtonPermission": "角色接口权限表",
    "Dept": "部门表",
    "Button": "权限标识表",
    "Menu": "菜单表",
    "MenuField": "菜单字段表",
    "FieldPermission": "字段权限表",
    "MenuButton": "菜单权限表",
    "Dictionary": "字典表",
    "OperationLog": "操作日志",
    "LoginLog": "登录日志",
    "Notification": "消息通知",
    "NotificationUsers": "消息用户",
    "SystemConfig": "系统配置表",
}

# 排除的非业务模型（对齐 Django 版 exclude_models 与默认排除 app）
_EXCLUDE_MODELS = {"CaptchaStore", "UsersRole", "RoleMenuPermissionDept",
                   "RoleMenuButtonPermissionDept", "MessageDept", "MessageRole"}


def _sa_type_to_internal(col) -> str:
    """SQLAlchemy 列类型 → Django internal type 名（对齐 field.get_internal_type()）"""
    tname = type(col.type).__name__
    mapping = {
        "String": "CharField",
        "Text": "TextField",
        "Integer": "IntegerField",
        "BigInteger": "BigIntegerField",
        "SmallInteger": "SmallIntegerField",
        "Boolean": "BooleanField",
        "DateTime": "DateTimeField",
    }
    if col.primary_key and col.autoincrement is not False and tname in ("Integer", "BigInteger"):
        return "BigAutoField" if tname == "BigInteger" else "AutoField"
    return mapping.get(tname, tname)


def get_project_app_models(app_name=None, exclude_apps=None, include_fields=True):
    """
    获取项目所有自定义模型信息（对应 Django utils/models.get_project_app_models）
    返回: [{'app', 'verbose', 'model', 'object', 'fields': [{'title','name','type'}]}]
    """
    from mysystem import models as m
    result = []
    for name in dir(m):
        cls = getattr(m, name)
        if not (isinstance(cls, type) and hasattr(cls, "__tablename__")):
            continue
        if name in _EXCLUDE_MODELS or name not in _MODEL_VERBOSE_NAMES:
            continue
        fields = []
        if include_fields:
            for col in cls.__table__.columns:
                fields.append({
                    'title': col.comment or '',
                    'name': col.name,
                    'type': _sa_type_to_internal(col),
                })
        result.append({
            'app': 'mysystem',
            'verbose': _MODEL_VERBOSE_NAMES[name],
            'model': name,
            'object': cls,
            'fields': fields,
        })
    return result


def get_all_models_objects(model_name=None, exclude_modules=None, include_fields=True):
    """
    获取所有模型对象信息（对应 Django utils/models.get_all_models_objects）
    返回: {ModelName: {"table": {...}, "object": model}}
    """
    result = {}
    for info in get_project_app_models(include_fields=include_fields):
        table_info = {
            "table_name": info['verbose'],
            "db_table": info['object'].__tablename__,
            "class_name": info['model'],
            "import_path": f"from mysystem.models import {info['model']}",
            "tableFields": [
                {'title': f['title'], 'name': f['name'], 'type': f['type']}
                for f in info['fields']
            ],
        }
        result[info['model']] = {"table": table_info, "object": info['object']}
    if model_name:
        return result.get(model_name, {})
    return result
