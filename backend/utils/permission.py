# -*- coding: utf-8 -*-
"""
@Remark: 认证与权限验证模块（对应 Django utils/permission.py + JWTAuthentication）
(1) get_current_user：FastAPI 依赖，JWT 认证（与 simplejwt 行为/错误消息对齐）
(2) APIPermissionValidator + require_api_permission：CustomPermission 完整移植
"""
import re
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.database import get_db
from config import CUSTOM_PERMISSION_CAHCE, CUSTOM_PERMISSION_CAHCE_TIME, CUSTOM_PERMISSION_WHITELIST, IS_DEMO
from mysystem.models import MenuButton, RoleMenuButtonPermission, SystemConfig, Users, get_user_role_ids
from utils.common import safe_parse_json
from utils.exception import AuthenticationError, PermissionDeniedError
from utils.security import TokenError, decode_token

# ================================================= #
# ************** JWT 认证依赖 ************** #
# ================================================= #

# 对齐 simplejwt JWTAuthentication 的认证头解析与错误消息
# 消息文案对齐 Django 侧 DRF zh-Hans 本地化结果（NotAuthenticated → 身份认证信息未提供。）
NOT_AUTHENTICATED_MSG = "身份认证信息未提供。"
TOKEN_NOT_VALID_MSG = "Given token not valid for any token type"


def _extract_raw_token(request: Request) -> Optional[str]:
    """解析 Authorization: JWT <token>（对齐 simplejwt.authenticate 逻辑）"""
    header = request.headers.get('Authorization', '')
    if not header:
        return None
    parts = header.split()
    if len(parts) == 0 or parts[0] != 'JWT':
        return None
    if len(parts) != 2:
        return None
    return parts[1]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Users:
    """
    JWT 认证依赖（对应 rest_framework_simplejwt.JWTAuthentication.authenticate）
    失败一律抛 AuthenticationError（HTTP 200 + 业务码 4001，消息与 Django 版一致）
    """
    raw_token = _extract_raw_token(request)
    if raw_token is None:
        raise AuthenticationError(NOT_AUTHENTICATED_MSG)

    try:
        payload = decode_token(raw_token, expected_type="access")
    except TokenError:
        # 对齐 InvalidToken("Given token not valid for any token type")
        # → CustomExceptionHandler 映射 msg "身份认证已过期"
        raise AuthenticationError("身份认证已过期")

    user = db.get(Users, payload.get("user_id"))
    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("该账号已被禁用,请联系管理员")
    return user


# ================================================= #
# ************** API 权限验证（CustomPermission 移植） ************** #
# ================================================= #


class APIPermissionValidator:
    """API权限验证工具类（与 Django 版逐行对齐）"""

    CAN_CACHE = CUSTOM_PERMISSION_CAHCE
    CACHE_TIMEOUT = CUSTOM_PERMISSION_CAHCE_TIME

    @staticmethod
    def validate_api_path(request_path: str, permission_api: str) -> bool:
        """
        使用正则验证请求路径是否匹配权限路径（{id} 等路径参数转换为正则）
        注意：与 Django 版一致，不做 re.escape，直接替换
        """
        if not permission_api:
            return False
        pattern = permission_api.replace('{id}', r'.*?').replace('/', r'\/')
        return bool(re.fullmatch(pattern, request_path))

    @classmethod
    def get_user_permissions(cls, db: Session, user_id, role_ids):
        """获取用户权限数据 (api, method) 列表（可缓存）"""
        if cls.CAN_CACHE:
            # 阶段5 接入统一缓存后启用；当前与 Django 配置一致默认不启用
            pass
        rows = db.execute(
            select(MenuButton.api, MenuButton.method)
            .join(RoleMenuButtonPermission, RoleMenuButtonPermission.menu_button_id == MenuButton.id)
            .where(RoleMenuButtonPermission.role_id.in_(role_ids))
        ).all()
        return list(rows)


def check_api_permission(request: Request, db: Session, user: Users) -> bool:
    """核心权限验证逻辑（对齐 CustomPermission._check_api_permission）"""
    role_ids = get_user_role_ids(db, user.id)
    user_permissions = APIPermissionValidator.get_user_permissions(db, user.id, role_ids)

    current_api = request.url.path
    current_method = request.method
    methodList = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH']
    current_method = methodList.index(current_method)

    for perm_api, perm_method in user_permissions:
        if (current_method == perm_method and
                APIPermissionValidator.validate_api_path(current_api, perm_api)):
            return True
    return False


def _match_param_path(pattern_path: str, request_path: str) -> bool:
    """匹配含参数的路径（对齐 CustomPermission._match_param_path）"""
    pattern = pattern_path.replace('{id}', r'([a-zA-Z0-9-]+)').replace('/', r'\/')
    return bool(re.fullmatch(pattern, request_path))


def get_db_whitelist(db: Session) -> list:
    """从数据库获取白名单列表（SystemConfig key=apiWhiteList）"""
    ins = db.execute(
        select(SystemConfig).where(SystemConfig.key == "apiWhiteList")
    ).scalars().first()
    if not ins:
        return []
    wlist = safe_parse_json(ins.value)
    if not wlist:
        return []
    return [(item.get("api"), item.get("method")) for item in wlist]


def check_whitelist(db: Session, request_path: str, current_method: str) -> bool:
    """检查请求是否在白名单中（config 白名单 + 数据库白名单合并）"""
    combined_whitelist = set(CUSTOM_PERMISSION_WHITELIST) | set(get_db_whitelist(db))
    for (whitelist_path, whitelist_method) in combined_whitelist:
        if current_method != whitelist_method and whitelist_method != "ALL":
            continue
        if current_path_match(whitelist_path, request_path):
            return True
    return False


def current_path_match(whitelist_path: str, current_path: str) -> bool:
    """精确匹配完整路径或 {id} 参数路径"""
    if current_path == whitelist_path:
        return True
    if '{id}' in whitelist_path:
        return _match_param_path(whitelist_path, current_path)
    return False


def require_api_permission(request: Request, db: Session, user: Users) -> None:
    """
    接口权限守卫（对齐 CustomPermission.has_permission，不通过抛 PermissionDeniedError）
    判定顺序：超级管理员 → 白名单 → 演示模式 → step_permission(阶段2) → API权限
    """
    # 超级管理员放行
    if user.is_superuser:
        return

    current_path = request.url.path
    current_method = request.method.upper()

    # 白名单
    if check_whitelist(db, current_path, current_method):
        return

    # 演示模式检查
    if IS_DEMO and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        raise PermissionDeniedError('演示环境禁止修改操作')

    # 验证API权限（不通过 → 对齐 DRF PermissionDenied 的 zh-Hans 文案）
    if not check_api_permission(request, db, user):
        raise PermissionDeniedError("您没有执行该操作的权限。")
