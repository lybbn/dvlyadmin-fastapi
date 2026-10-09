# -*- coding: utf-8 -*-
"""
@Remark: SQLAlchemy 模型（对应 Django mysystem/models.py）
重要约定：
(1) 只映射既有表结构（表结构与 backend/mysystem/migrations/0001_initial.py 严格对齐），
    本层绝不建表/改表，表结构由 Django 迁移体系管理；独立开发（不依赖 Django）时
    由 `python run.py db_init` 命令建表（见 application/database.py 说明）
(2) Django FK(db_constraint=False) 落库为无约束的 *_id 列 → 本层用普通列表达关联
(3) auto_now/auto_now_add → onupdate/default=datetime.now（Django USE_TZ=False，本地 naive 时间）
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, SmallInteger, String, Text, UniqueConstraint

from application.database import Base
from utils.models import CoreModelMixin, BaseModelMixin, make_uuid, table_prefix

# ================================================= #
# ************** 用户体系 ************** #
# ================================================= #


class Users(Base, CoreModelMixin):
    """用户表（lyadmin_users，对应 Django Users(AbstractBaseUser, CoreModel)）"""

    __tablename__ = table_prefix + "users"
    __default_ordering__ = ("-create_datetime",)  # 对齐 Django Meta.ordering

    password = Column(String(128), nullable=False, comment="密码")
    last_login = Column(DateTime, nullable=True, comment="上次登录")
    username = Column(String(50), nullable=False, unique=True, index=True, comment="用户账号")
    email = Column(String(60), nullable=True, comment="邮箱")
    mobile = Column(String(30), nullable=True, comment="电话")
    avatar = Column(String(200), nullable=True, comment="头像")
    name = Column(String(40), nullable=False, comment="姓名")
    nickname = Column(String(100), nullable=True, default="", comment="用户昵称")
    gender = Column(SmallInteger, nullable=True, default=0, comment="性别")
    login_error_nums = Column(Integer, nullable=True, default=0, comment="登录错误次数")
    identity = Column(SmallInteger, nullable=True, default=2, comment="身份标识")
    is_delete = Column(Boolean, nullable=True, default=False, comment="是否逻辑删除")
    is_active = Column(Boolean, nullable=True, default=True, comment="状态")
    is_staff = Column(Boolean, nullable=True, default=False, comment="是否员工")
    is_superuser = Column(Boolean, nullable=True, default=False, comment="是否超级管理员")
    dept_id = Column(String(100), nullable=True, comment="所属部门")

    # 审计字段继承自 CoreModelMixin（creator_id/modifier/dept_belong/时间字段）


class Role(Base, CoreModelMixin):
    """角色表（lyadmin_role）"""

    __tablename__ = table_prefix + "role"
    __default_ordering__ = ("sort",)

    name = Column(String(64), nullable=False, unique=True, comment="角色名称")
    key = Column(String(64), nullable=False, unique=True, comment="权限字符")
    sort = Column(Integer, nullable=True, default=1, comment="角色顺序")
    status = Column(Boolean, nullable=True, default=True, comment="角色状态")
    remark = Column(String(255), nullable=True, comment="备注")


class Dept(Base, CoreModelMixin):
    """部门表（lyadmin_dept）"""

    __tablename__ = table_prefix + "dept"
    __default_ordering__ = ("sort",)

    name = Column(String(64), nullable=False, comment="部门名称")
    key = Column(String(64), nullable=True, unique=True, comment="关联字符")
    sort = Column(Integer, nullable=True, default=1, comment="显示排序")
    owner = Column(String(32), nullable=True, comment="负责人")
    phone = Column(String(32), nullable=True, comment="联系电话")
    email = Column(String(32), nullable=True, comment="邮箱")
    status = Column(Boolean, nullable=True, default=True, comment="角色状态")
    parent_id = Column(String(100), nullable=True, comment="上级部门")


class UsersRole(Base):
    """用户-角色多对多（lyadmin_users_role，Django 自动生成表）"""

    __tablename__ = table_prefix + "users_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    users_id = Column(String(100), nullable=False, comment="用户")
    role_id = Column(String(100), nullable=False, comment="角色")


# ================================================= #
# ************** 菜单权限体系 ************** #
# ================================================= #


class Menu(Base, CoreModelMixin):
    """菜单表（lyadmin_menu）"""

    __tablename__ = table_prefix + "menu"
    __default_ordering__ = ("sort",)

    parent_id = Column(String(100), nullable=True, comment="上级菜单")
    icon = Column(String(64), nullable=True, comment="菜单图标")
    name = Column(String(64), nullable=False, comment="菜单名称")
    sort = Column(Integer, nullable=True, default=1, comment="显示排序")
    type = Column(SmallInteger, nullable=True, default=0, comment="是否外链")
    link_url = Column(String(255), nullable=True, comment="链接地址")
    web_path = Column(String(128), nullable=True, comment="路由地址")
    component = Column(String(128), nullable=True, comment="组件地址")
    component_name = Column(String(50), nullable=True, comment="组件名称")
    status = Column(Boolean, nullable=True, default=True, comment="按钮状态")
    isautopm = Column(Boolean, nullable=True, default=False, comment="自动创建按钮权限")
    cache = Column(Boolean, nullable=True, default=False, comment="是否页面缓存")
    visible = Column(Boolean, nullable=True, default=True, comment="侧边栏中是否显示")


class MenuButton(Base):
    """菜单权限表（lyadmin_menu_button，自增主键）"""

    __tablename__ = table_prefix + "menu_button"
    __default_ordering__ = ("-name",)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, comment="名称")
    value = Column(String(64), nullable=False, comment="权限值")
    api = Column(String(64), nullable=False, comment="接口地址")
    method = Column(SmallInteger, nullable=True, default=0, comment="接口请求方法")
    menu_id = Column(String(100), nullable=False, comment="关联菜单")


class MenuField(Base):
    """菜单字段表（lyadmin_menu_field，自增主键）"""

    __tablename__ = table_prefix + "menu_field"
    __default_ordering__ = ("id",)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model = Column(String(70), nullable=True, comment="所属模型Model")
    field_name = Column(String(64), nullable=False, comment="模型表字段名")
    title = Column(String(64), nullable=False, comment="字段显示名")
    menu_id = Column(String(100), nullable=False, comment="关联菜单")


class FieldPermission(Base):
    """字段权限表（lyadmin_field_permission，自增主键）"""

    __tablename__ = table_prefix + "field_permission"
    __default_ordering__ = ("id",)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    can_view = Column(Boolean, nullable=True, default=True, comment="查看权限")
    can_create = Column(Boolean, nullable=True, default=True, comment="创建权限")
    can_update = Column(Boolean, nullable=True, default=True, comment="更新权限")
    field_id = Column(BigInteger, nullable=False, comment="字段")
    role_id = Column(String(100), nullable=False, comment="关联角色")


class Button(Base, CoreModelMixin):
    """权限标识表（lyadmin_button）"""

    __tablename__ = table_prefix + "button"
    __default_ordering__ = ("-name",)

    name = Column(String(64), nullable=False, comment="权限名称")
    value = Column(String(64), nullable=False, comment="权限值")
    status = Column(Boolean, nullable=True, default=True, comment="状态")


class RoleMenuPermission(Base):
    """角色菜单权限表（lyadmin_role_menu_permission，自增主键）"""

    __tablename__ = table_prefix + "role_menu_permission"
    __default_ordering__ = ("-id",)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    data_scope = Column(SmallInteger, nullable=True, default=4, comment="数据权限")
    menu_id = Column(String(100), nullable=False, comment="关联菜单")
    role_id = Column(String(100), nullable=False, comment="关联角色")


class RoleMenuPermissionDept(Base):
    """角色菜单权限-部门多对多（lyadmin_role_menu_permission_dept，Django 自动生成表）"""

    __tablename__ = table_prefix + "role_menu_permission_dept"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rolemenupermission_id = Column(BigInteger, nullable=False, comment="角色菜单权限")
    dept_id = Column(String(100), nullable=False, comment="部门")


class RoleMenuButtonPermission(Base):
    """角色接口权限表（lyadmin_role_menubutton_permission，自增主键）"""

    __tablename__ = table_prefix + "role_menubutton_permission"
    __default_ordering__ = ("-id",)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    data_scope = Column(SmallInteger, nullable=True, default=5, comment="数据权限")
    menu_button_id = Column(BigInteger, nullable=True, comment="关联菜单按钮")
    role_id = Column(String(100), nullable=False, comment="关联角色")


class RoleMenuButtonPermissionDept(Base):
    """角色接口权限-部门多对多（lyadmin_role_menubutton_permission_dept，Django 自动生成表）"""

    __tablename__ = table_prefix + "role_menubutton_permission_dept"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rolemenubuttonpermission_id = Column(BigInteger, nullable=False, comment="角色接口权限")
    dept_id = Column(String(100), nullable=False, comment="部门")


# ================================================= #
# ************** 字典/日志/消息/配置 ************** #
# ================================================= #


class Dictionary(Base, CoreModelMixin):
    """字典表（lyadmin_dictionary）"""

    __tablename__ = table_prefix + "dictionary"
    __default_ordering__ = ("sort",)

    label = Column(String(100), nullable=True, comment="字典名称")
    value = Column(String(200), nullable=True, comment="字典编号/实际值")
    status = Column(Boolean, nullable=True, default=True, comment="状态")
    sort = Column(Integer, nullable=True, default=1, comment="显示排序")
    remark = Column(String(255), nullable=True, comment="备注")
    parent_id = Column(String(100), nullable=True, comment="父级")


class OperationLog(Base, CoreModelMixin):
    """操作日志（lyadmin_operation_log）"""

    __tablename__ = table_prefix + "operation_log"
    __default_ordering__ = ("-create_datetime",)

    creator_name = Column(String(30), nullable=True, comment="操作人")
    req_modular = Column(String(64), nullable=True, comment="请求模块")
    req_path = Column(Text, nullable=True, comment="请求地址")
    req_body = Column(Text, nullable=True, comment="请求参数")
    req_method = Column(String(8), nullable=True, comment="请求方式")
    req_msg = Column(Text, nullable=True, comment="操作说明")
    req_ip = Column(String(32), nullable=True, comment="请求ip地址")
    req_browser = Column(String(64), nullable=True, comment="请求浏览器")
    resp_code = Column(String(32), nullable=True, comment="响应状态码")
    req_os = Column(String(64), nullable=True, comment="操作系统")
    ip_area = Column(String(100), nullable=True, comment="IP归属地")
    json_result = Column(Text, nullable=True, comment="返回信息")
    status = Column(Boolean, nullable=True, default=False, comment="响应状态")


class LoginLog(Base, CoreModelMixin):
    """登录日志（lyadmin_login_log）"""

    __tablename__ = table_prefix + "login_log"
    __default_ordering__ = ("-create_datetime",)

    username = Column(String(32), nullable=True, comment="登录用户名")
    ip = Column(String(32), nullable=True, comment="登录ip")
    agent = Column(String(1500), nullable=True, comment="agent信息")
    browser = Column(String(200), nullable=True, comment="浏览器名")
    os = Column(String(150), nullable=True, comment="操作系统")
    login_type = Column(Integer, nullable=True, default=1, comment="登录类型")
    ip_area = Column(String(100), nullable=True, comment="IP归属地")
    msg = Column(String(255), nullable=True, comment="自定义内容")
    status = Column(Boolean, nullable=True, default=True, comment="响应状态")


class Notification(Base, CoreModelMixin):
    """消息通知（lyadmin_message）"""

    __tablename__ = table_prefix + "message"
    __default_ordering__ = ("-create_datetime",)

    title = Column(String(100), nullable=False, comment="标题")
    content = Column(Text, nullable=False, comment="内容")
    target_type = Column(SmallInteger, nullable=True, default=0, comment="目标类型")
    tag_type = Column(SmallInteger, nullable=True, default=0, comment="标签类型")


class NotificationUsers(Base):
    """消息用户（lyadmin_message_users，自增主键）"""

    __tablename__ = table_prefix + "message_users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    is_read = Column(Boolean, nullable=True, default=False, comment="是否已读")
    read_at = Column(DateTime, nullable=True, comment="已读时间")
    is_delete = Column(Boolean, nullable=True, default=False, comment="是否逻辑删除")
    notification_id = Column(String(100), nullable=False, comment="关联消息")
    user_id = Column(String(100), nullable=False, comment="关联用户表")


class MessageDept(Base):
    """消息-部门多对多（lyadmin_message_dept，Django 自动生成表）"""

    __tablename__ = table_prefix + "message_dept"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(String(100), nullable=False, comment="消息")
    dept_id = Column(String(100), nullable=False, comment="部门")


class MessageRole(Base):
    """消息-角色多对多（lyadmin_message_role，Django 自动生成表）"""

    __tablename__ = table_prefix + "message_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(String(100), nullable=False, comment="消息")
    role_id = Column(String(100), nullable=False, comment="角色")


class SystemConfig(Base, CoreModelMixin):
    """系统配置表（lyadmin_system_config）"""

    __tablename__ = table_prefix + "system_config"
    __default_ordering__ = ("sort",)
    __table_args__ = (UniqueConstraint("key", "parent_id", name="lyadmin_system_config_key_parent_id_unique"),)

    title = Column(String(50), nullable=False, comment="标题")
    key = Column(String(20), nullable=False, index=True, comment="键名")
    value = Column(Text, nullable=True, comment="键值")
    sort = Column(Integer, nullable=True, default=0, comment="排序")
    status = Column(Boolean, nullable=True, default=True, comment="启用状态")
    data_options = Column(Text, nullable=True, comment="数据options")
    form_item_type = Column(SmallInteger, nullable=True, default=0, comment="表单类型")
    rule = Column(Text, nullable=True, comment="校验规则")
    placeholder = Column(String(50), nullable=True, comment="提示信息")
    tip = Column(String(100), nullable=True, comment="底部提示说明")
    setting = Column(Text, nullable=True, comment="配置")
    parent_id = Column(String(100), nullable=True, comment="父级")


# ================================================= #
# ************** 验证码（django-simple-captcha 同表） ************** #
# ================================================= #


class CaptchaStore(Base):
    """验证码存储（captcha_captchastore，与 Django simple-captcha 共用）"""

    __tablename__ = "captcha_captchastore"

    id = Column(Integer, primary_key=True, autoincrement=True)
    challenge = Column(String(32), nullable=False, comment="挑战文本")
    response = Column(String(32), nullable=False, comment="响应结果")
    hashkey = Column(String(40), nullable=False, unique=True, comment="哈希键")
    expiration = Column(DateTime, nullable=False, comment="过期时间")


def get_user_role_ids(db, user_id):
    """获取用户角色ID列表（对齐 Django user.role.values_list('id', flat=True)）"""
    from sqlalchemy import select
    return [r[0] for r in db.execute(
        select(UsersRole.role_id).where(UsersRole.users_id == user_id)
    ).all()]


def get_user_roles(db, user_id):
    """获取用户角色对象列表（对齐 Django user.role.filter(status=True) 由调用方过滤）"""
    from sqlalchemy import select
    return db.execute(
        select(Role).join(UsersRole, UsersRole.role_id == Role.id).where(UsersRole.users_id == user_id)
    ).scalars().all()


# ================================================= #
# ************** 删除级联规则（对齐 Django ORM Collector） ************** #
# ================================================= #
# Django 的 queryset.delete() 会级联删除所有 on_delete=CASCADE 的关联行（即使 db_constraint=False），
# 并对 on_delete=PROTECT 的引用抛 ProtectedError；SQLAlchemy 无此机制 → 声明式规则 + 通用执行函数
# （utils/viewset.py 的 apply_cascade）在 destroy/multiple_delete 中对齐。
# 规则格式：主体模型类名 → {"cascade": [(子模型类名 或 "@table:裸表名", 引用列名)], "protect": [(模型类名, 列名)]}
# - 链式级联（如 Menu→MenuButton→RoleMenuButtonPermission）与自关联子树（Menu/Dept/SystemConfig 的 parent_id）自动递归
# - "@table:" 前缀用于 Django m2m 自动生成、本端无模型类的 through 表
CASCADE_RULES = {
    "Menu": {
        "cascade": [("MenuButton", "menu_id"), ("MenuField", "menu_id"),
                    ("RoleMenuPermission", "menu_id"), ("Menu", "parent_id")],
    },
    "MenuButton": {
        "cascade": [("RoleMenuButtonPermission", "menu_button_id")],
    },
    "MenuField": {
        "cascade": [("FieldPermission", "field_id")],
    },
    "RoleMenuPermission": {
        "cascade": [("RoleMenuPermissionDept", "rolemenupermission_id")],
    },
    "RoleMenuButtonPermission": {
        "cascade": [("RoleMenuButtonPermissionDept", "rolemenubuttonpermission_id")],
    },
    "Role": {
        "cascade": [("RoleMenuPermission", "role_id"), ("RoleMenuButtonPermission", "role_id"),
                    ("FieldPermission", "role_id"), ("UsersRole", "role_id"),
                    ("@table:lyadmin_message_role", "role_id")],
    },
    "Dept": {
        "cascade": [("Dept", "parent_id"), ("RoleMenuPermissionDept", "dept_id"),
                    ("RoleMenuButtonPermissionDept", "dept_id"),
                    ("@table:lyadmin_message_dept", "dept_id")],
        "protect": [("Users", "dept_id")],  # 对齐 Users.dept on_delete=PROTECT
    },
    "Users": {
        "cascade": [("UsersRole", "users_id"), ("NotificationUsers", "user_id")],
    },
    "Notification": {
        "cascade": [("NotificationUsers", "notification_id")],
    },
    "SystemConfig": {
        "cascade": [("SystemConfig", "parent_id")],  # 删父配置级联删子配置
    },
    "Dictionary": {
        "protect": [("Dictionary", "parent_id")],  # 对齐 Dictionary.parent on_delete=PROTECT
    },
}


def get_cascade_model(name):
    """按类名解析本模块的模型类（CASCADE_RULES 用）"""
    return globals()[name]
