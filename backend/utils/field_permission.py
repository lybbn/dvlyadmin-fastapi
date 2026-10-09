# -*- coding: utf-8 -*-
"""
@Remark: 自定义列权限（对应 Django utils/field_permission.py 的 FieldPermissionMixin）
(1) /field_permission/ 查询接口
(2) 输出时按 can_view 剔除字段，输入时按 can_create/can_update 剔除字段
(3) 超级管理员自动拥有全部权限
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import FIELD_PERMISSION_CACHE
from mysystem.models import FieldPermission, MenuField, UsersRole


def get_field_permissions(db: Session, request, user, model_name: str) -> dict:
    """
    获取当前用户的字段权限规则（带缓存开关）
    返回: {"field_name": {"can_view": bool, "can_create": bool, "can_update": bool}}
    """
    # 超级管理员返回全部权限
    if getattr(user, 'is_superuser', False):
        return get_all_fields_permission(db, model_name)

    # 普通用户
    role_ids = [r[0] for r in db.execute(
        select(UsersRole.role_id).where(UsersRole.users_id == user.id)
    ).all()]

    if FIELD_PERMISSION_CACHE:
        # 阶段5接入统一缓存后启用
        pass

    return query_database_permissions(db, model_name, role_ids)


def get_all_fields_permission(db: Session, model_name: str) -> dict:
    """获取所有字段的完全权限"""
    fields = db.execute(
        select(MenuField.field_name).where(MenuField.model == model_name)
    ).all()
    return {
        field[0]: {"can_create": True, "can_view": True, "can_update": True}
        for field in fields
    }


def query_database_permissions(db: Session, model_name: str, role_ids) -> dict:
    """从数据库查询权限并合并（多角色 OR 逻辑）"""
    rows = db.execute(
        select(FieldPermission.can_create, FieldPermission.can_view, FieldPermission.can_update,
               MenuField.field_name)
        .join(MenuField, MenuField.id == FieldPermission.field_id)
        .where(MenuField.model == model_name, FieldPermission.role_id.in_(role_ids))
    ).all()
    data = [
        {"can_create": r[0], "can_view": r[1], "can_update": r[2], "field_name": r[3]}
        for r in rows
    ]
    return merge_permissions(data)


def merge_permissions(data: list) -> dict:
    """合并多个角色的权限（OR逻辑）"""
    result = {}
    for item in data:
        field_name = item['field_name']
        if field_name not in result:
            result[field_name] = item.copy()
        else:
            for perm in ['can_create', 'can_view', 'can_update']:
                result[field_name][perm] = result[field_name][perm] or item[perm]
    return result


def apply_field_permissions_to_output(permissions: dict, data: dict) -> dict:
    """输出序列化结果按 can_view 剔除字段（对齐 DynamicSerializer 的 fields.pop）"""
    if not permissions:
        return data
    return {
        k: v for k, v in data.items()
        if k not in permissions or permissions[k]['can_view']
    }


def apply_field_permissions_to_input(permissions: dict, data: dict, action: str) -> dict:
    """输入数据按 can_create/can_update 剔除（对齐 field.read_only=True 行为）"""
    if not permissions:
        return data
    result = {}
    for k, v in data.items():
        if k in permissions:
            perm = permissions[k]
            if action == 'create' and not perm['can_create']:
                continue
            if action in ('update', 'partial_update') and not perm['can_update']:
                continue
        result[k] = v
    return result
