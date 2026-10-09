# -*- coding: utf-8 -*-
"""
@Remark: 自定义过滤器（对应 Django utils/filters.py）
(1) get_dept_children_ids：递归子部门（含缓存开关）
(2) DataLevelPermissionsFilter.apply：数据级权限过滤（5级 scope，按钮优先于菜单）
(3) apply_filterset：filterset_fields / filterset_class 过滤（含 __range 双值区间）
(4) apply_search / apply_ordering：SearchFilter / OrderingFilter 等价
"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, DeclarativeMeta

from config import DATA_FILTER_CACHE, DATA_FILTER_CAHCE_TIME
from mysystem.models import (Dept, MenuButton, RoleMenuButtonPermission, RoleMenuButtonPermissionDept,
                             RoleMenuPermission, RoleMenuPermissionDept)


def get_dept_children_ids(db: Session, dept_id, include_self=False):
    """获取部门的所有子部门ID(包括自身可选)，递归所有层级"""
    result = None
    if DATA_FILTER_CACHE:
        result = _dept_children_cache.get(dept_id)  # 阶段5接入统一缓存后替换为 Redis
    if result is None:
        dept_all_list = db.execute(
            select(Dept.id, Dept.parent_id).where(Dept.status == True)  # noqa: E712
        ).all()
        dept_all_list = [{"id": r[0], "parent_id": r[1]} for r in dept_all_list]
        result = _get_dept_children_recursive(dept_id, dept_all_list)
        if DATA_FILTER_CACHE:
            _dept_children_cache[dept_id] = result
    if not include_self:
        result = [i for i in result if i != dept_id]
    return result


_dept_children_cache = {}


def _get_dept_children_recursive(dept_id, dept_all_list, dept_list=None):
    """递归获取子部门的内部方法"""
    if dept_list is None:
        dept_list = [dept_id]
    for dept in dept_all_list:
        if dept.get("parent_id", "") == dept_id:
            dept_list.append(dept.get("id"))
            _get_dept_children_recursive(dept["id"], dept_all_list, dept_list)
    return list(set(dept_list))  # 去重


class DataLevelPermissionsFilter:
    """
    数据级权限过滤器（对齐 Django 版，权限级别 5 优先级最高）
    0-仅本人 1-本部门 2-本部门及以下 3-自定义部门 4-全部 5-同全局(按菜单)
    """

    @staticmethod
    def apply(db: Session, request, user, query, model, path_pk=None):
        # 超级管理员直接返回所有数据
        if user.is_superuser:
            return query

        # 0. 获取用户部门信息
        user_dept_id = getattr(user, "dept_id", None)
        # 无部门用户只能查看自己的数据
        if not user_dept_id:
            if hasattr(model, "creator_id"):
                return query.where(model.creator_id == user.id)
            return query.where(False)

        # 1. 检查模型是否有归属字段（Django hasattr(model,'dept_belong')）
        if not hasattr(model, "dept_belong"):
            return query

        # 2. 获取用户所有有效角色的数据权限
        from mysystem.models import Role, UsersRole
        role_ids = [r[0] for r in db.execute(
            select(Role.id).join(UsersRole, UsersRole.role_id == Role.id)
            .where(UsersRole.users_id == user.id, Role.status == True)  # noqa: E712
        ).all()]
        if not role_ids:  # 没有关联角色则返回本部门数据
            return query.where(model.dept_belong == user_dept_id)

        api = request.url.path
        method = request.method
        methodList = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH']
        method = methodList.index(method)
        re_api = api
        # 从URL参数中提取主键pk，替换为 {id}
        _upk = path_pk
        if _upk:
            re_api = re_api.replace(str(_upk), '{id}')

        # 3. 先匹配接口数据权限（按钮优先）
        menu_button_ids = []
        menu_ids = []
        mb_rows = db.execute(
            select(MenuButton.id, MenuButton.menu_id).where(MenuButton.api == re_api, MenuButton.method == method)
        ).all()
        if mb_rows:
            menu_button_ids = [r[0] for r in mb_rows]
            menu_ids = [r[1] for r in mb_rows]

        role_permissions = []
        if menu_button_ids:
            role_permissions = [r[0] for r in db.execute(
                select(RoleMenuButtonPermission.data_scope)
                .where(RoleMenuButtonPermission.role_id.in_(role_ids),
                       RoleMenuButtonPermission.menu_button_id.in_(menu_button_ids))
            ).all()]

        max_data_scope = _get_max_data_scope(role_permissions)
        is_menu = False
        if max_data_scope in [5, -1]:  # 按钮未配置则按菜单全局数据权限
            is_menu = True
            if menu_ids:
                role_menu_permissions = [r[0] for r in db.execute(
                    select(RoleMenuPermission.data_scope)
                    .where(RoleMenuPermission.role_id.in_(role_ids),
                           RoleMenuPermission.menu_id.in_(menu_ids))
                ).all()]
                max_data_scope = _get_max_data_scope(role_menu_permissions)
            else:
                max_data_scope = 4  # 菜单数据权限默认【全部数据权限】

        # 3.1 最高权限直接返回
        if max_data_scope == 4:
            return query

        # 4. 仅本人数据
        if max_data_scope == 0:
            return query.where(model.creator_id == user.id)

        # 5. 获取允许过滤的部门列表
        dept_ids = _get_permitted_dept_ids(db, user_dept_id, role_ids, max_data_scope, is_menu)

        # 6. 应用部门过滤（dept 模型特殊：过滤自身 id）
        if isinstance(model, DeclarativeMeta) and getattr(model, "__name__", "") == "Dept":
            return query.where(model.id.in_(dept_ids))
        return query.where(model.dept_belong.in_(dept_ids))


def _get_max_data_scope(data_scopes):
    """去重取最大数据权限范围（默认-1）"""
    data_scopes = list(set(data_scopes))
    return max(data_scopes) if data_scopes else -1


def _get_permitted_dept_ids(db: Session, user_dept_id, role_ids, max_data_scope, is_menu=True):
    """根据权限级别获取允许访问的部门ID列表"""
    dept_ids = set()
    if max_data_scope == 1:  # 本部门
        dept_ids.add(user_dept_id)
    elif max_data_scope == 2:  # 本部门及以下
        dept_ids.update(get_dept_children_ids(db, user_dept_id, include_self=True))
    elif max_data_scope == 3:  # 自定义部门
        if is_menu:
            rows = db.execute(
                select(RoleMenuPermissionDept.dept_id)
                .join(RoleMenuPermission, RoleMenuPermission.id == RoleMenuPermissionDept.rolemenupermission_id)
                .where(RoleMenuPermission.role_id.in_(role_ids), RoleMenuPermission.data_scope == 3)
            ).all()
        else:
            rows = db.execute(
                select(RoleMenuButtonPermissionDept.dept_id)
                .join(RoleMenuButtonPermission, RoleMenuButtonPermission.id == RoleMenuButtonPermissionDept.rolemenubuttonpermission_id)
                .where(RoleMenuButtonPermission.role_id.in_(role_ids), RoleMenuButtonPermission.data_scope == 3)
            ).all()
        dept_ids.update([r[0] for r in rows])
    return list(dept_ids) if dept_ids else [user_dept_id]  # 默认至少本部门


# ================================================= #
# ************** filterset / search / ordering ************** #
# ================================================= #

# django-filter CharFilter lookup → SQLAlchemy 操作
def _lookup_op(model, field_path: str, lookup: str, value):
    """把 field_name + lookup_expr 转成 SQLAlchemy 条件（支持一层 __ 关联）"""
    # 解析字段（含外键列名映射）
    col = _resolve_column(model, field_path)
    if col is None:
        return None
    if lookup == "gte":
        return col >= value
    if lookup == "lte":
        return col <= value
    if lookup == "gt":
        return col > value
    if lookup == "lt":
        return col < value
    if lookup == "icontains":
        return col.ilike(f"%{value}%")
    if lookup == "contains":
        return col.like(f"%{value}%")
    if lookup == "istartswith":
        return col.ilike(f"{value}%")
    if lookup == "iendswith":
        return col.ilike(f"%{value}")
    if lookup == "iexact":
        return col.ilike(value)
    if lookup == "exact" or lookup is None:
        return col == value
    if lookup == "in":
        return col.in_(value if isinstance(value, (list, tuple)) else [value])
    if lookup == "isnull":
        return col.is_(None) if value in (True, "True", "true", 1) else col.is_not(None)
    if lookup == "range":
        return col.between(value[0], value[1])
    # 默认精确
    return col == value


def _resolve_column(model, field_path: str):
    """解析字段路径（支持 dept__name 一层跨表：返回标量子查询列）"""
    if "__" in field_path:
        parts = field_path.split("__")
        if len(parts) != 2:
            return None
        rel_name, target = parts
        # 本项目中跨表过滤仅 creator_username / creator_name / dept__name 等场景，
        # 由各 ViewSet 的 filterset_class 自行实现，这里仅支持 FK id 直接引用
        fk_col = f"{rel_name}_id"
        if hasattr(model, fk_col) and target == "id":
            return getattr(model, fk_col)
        return None
    if hasattr(model, field_path):
        return getattr(model, field_path)
    # FK 名称 → *_id 列
    if hasattr(model, f"{field_path}_id"):
        return getattr(model, f"{field_path}_id")
    return None


def apply_filterset(db: Session, request, query, model, filterset_fields, filterset_class=None):
    """
    对齐 CustomDjangoFilterBackend：
    (1) filterset_class：django_filters FilterSet 声明式过滤（FastAPI 版为可调用对象）
    (2) filterset_fields：元组精确过滤；同一参数传两次 → __range 区间
    """
    if filterset_class is not None:
        return filterset_class(db, request, query)
    if not filterset_fields:
        return query
    conditions = []
    for field in filterset_fields:
        values = request.query_params.getlist(field)
        if not values:
            continue
        values = [v for v in values if v != '']
        if not values:
            continue
        if len(values) == 2:  # 对齐 filterset_data_len == 2 → __range
            cond = _lookup_op(model, field, "range", values)
        else:
            cond = _lookup_op(model, field, "exact", values[0])
        if cond is not None:
            conditions.append(cond)
    if conditions:
        for cond in conditions:
            query = query.where(cond)
    return query


def apply_search(request, query, model, search_fields):
    """对齐 DRF SearchFilter：?search= xxx，OR icontains（支持 ^ = $ 前缀）"""
    search_term = request.query_params.get("search", "")
    if not search_term or not search_fields:
        return query
    conditions = []
    for field in search_fields:
        lookup = "icontains"
        if field and field[0] in "^=$@~":
            prefix_map = {"^": "istartswith", "=": "iexact", "$": "iendswith", "@": "icontains", "~": "icontains"}
            lookup = prefix_map[field[0]]
            field = field[1:]
        col = _resolve_column(model, field)
        if col is None:
            continue
        value = search_term
        if lookup == "icontains":
            conditions.append(col.ilike(f"%{value}%"))
        elif lookup == "istartswith":
            conditions.append(col.ilike(f"{value}%"))
        elif lookup == "iexact":
            conditions.append(col.ilike(value))
        elif lookup == "iendswith":
            conditions.append(col.ilike(f"%{value}"))
    if conditions:
        query = query.where(or_(*conditions))
    return query


ORDERING_DIRECTIONS = ("-", "+")


def apply_ordering(request, query, model, ordering_fields):
    """
    对齐 DRF OrderingFilter：?ordering=-field,field2
    无效字段静默剔除；未传 ordering 时保持 query 已有排序（模型默认排序由 ViewSet 注入）
    """
    ordering = request.query_params.get("ordering", "")
    if not ordering:
        return query
    cols = {c.name for c in model.__table__.columns}
    fk_cols = {c.name for c in model.__table__.columns if c.name.endswith("_id") and c.name != "dept_belong"}
    terms = []
    for term in [t.strip() for t in ordering.split(",") if t.strip()]:
        desc = term.startswith("-")
        field = term[1:] if desc else term
        if ordering_fields != "__all__" and field not in ordering_fields:
            continue
        if field not in cols:
            if f"{field}_id" in fk_cols:
                field = f"{field}_id"
            else:
                continue
        col = getattr(model, field)
        terms.append(col.desc() if desc else col.asc())
    if terms:
        query = query.order_by(*terms)
    return query
