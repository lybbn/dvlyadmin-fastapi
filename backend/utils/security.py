# -*- coding: utf-8 -*-
"""
@Remark: 安全工具（密码哈希 + JWT）
(1) 密码：实现 Django pbkdf2_sha256$<iterations>$<salt>$<hash> 格式，
    与 Django 既有用户数据完全互通（可验证/可生成）
(2) JWT：与 djangorestframework-simplejwt 5.3.1 完全互通——
    HS256、SECRET_KEY 与 Django 一致、payload 对齐
    {token_type, exp(epoch秒), iat(epoch秒), jti(uuid4hex), user_id}
"""
import base64
import hashlib
import hmac
import random
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from application.settings import SECRET_KEY, SIMPLE_JWT

# Django get_random_string 的字符集（生成密码盐用，保证格式互通）
_RANDOM_STRING_CHARS = string.ascii_lowercase + string.ascii_uppercase + string.digits

# Django 4.1 默认迭代次数（backend/requirements.txt: Django==4.1.8）
DEFAULT_ITERATIONS = 390000

ALGORITHM = SIMPLE_JWT.get("ALGORITHM", "HS256")


def get_random_string(length: int) -> str:
    """对齐 Django django.utils.crypto.get_random_string"""
    return "".join(random.choice(_RANDOM_STRING_CHARS) for _ in range(length))


# ================================================= #
# ************** 密码（Django pbkdf2_sha256 互通） ************** #
# ================================================= #


def make_password(raw_password: str) -> str:
    """生成与 Django make_password 完全同格式的密码哈希"""
    salt = get_random_string(12)
    digest = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), DEFAULT_ITERATIONS)
    hash_b64 = base64.b64encode(digest).decode("ascii").strip()
    return f"pbkdf2_sha256${DEFAULT_ITERATIONS}${salt}${hash_b64}"


def check_password(raw_password: str, encoded: str) -> bool:
    """验证 Django 格式的 pbkdf2_sha256 密码"""
    try:
        algorithm, iterations, salt, hash_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
        return hmac.compare_digest(base64.b64encode(digest).decode("ascii").strip(), hash_b64)
    except Exception:
        return False


# ================================================= #
# ************** JWT（simplejwt 5.3.1 互通） ************** #
# ================================================= #


class TokenError(Exception):
    """对齐 simplejwt TokenError，args[0] 为用户可读消息"""


def _datetime_to_epoch(dt: datetime) -> int:
    # 对齐 simplejwt.utils.datetime_to_epoch（aware datetime → UTC epoch 秒）
    return int((dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())


def create_token(user_id, token_type: str, lifetime: timedelta) -> str:
    """签发与 simplejwt Token.for_user 相同 payload 的 JWT"""
    now = datetime.now(timezone.utc)
    payload = {
        "token_type": token_type,
        "exp": _datetime_to_epoch(now + lifetime),
        "iat": _datetime_to_epoch(now),
        "jti": uuid4().hex,
        "user_id": str(user_id),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    """
    解码并校验 JWT（对齐 simplejwt TokenBackend.decode + Token.verify）
    校验失败抛 TokenError，消息与 simplejwt 一致
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise TokenError("Token is invalid or expired")
    except jwt.InvalidTokenError:
        raise TokenError("Token is invalid or expired")

    if "jti" not in payload:
        raise TokenError("Token has no id")

    token_type = payload.get("token_type")
    if token_type is None:
        raise TokenError("Token has no type")
    if token_type != expected_type:
        raise TokenError("Token has wrong type")

    return payload


def create_access_and_refresh(user_id):
    """生成登录返回的 token 对（对齐 LoginSerializer.get_token）"""
    refresh = create_token(user_id, "refresh", SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
    access = create_token(user_id, "access", SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])
    return {"refresh": refresh, "access": access}


def rotate_refresh_token(refresh_token: str):
    """
    对齐 TokenRefreshSerializer.validate：
    校验 refresh token，ROTATE_REFRESH_TOKENS=True 时重签 refresh 并返回 {"access", "refresh"}
    失败抛 TokenError
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    return create_access_and_refresh(payload["user_id"])
