# -*- coding: utf-8 -*-
"""
@Remark: 自定义异常处理（对应 Django utils/exception.py）
与 DRF 版行为对齐的关键点：
(1) 取消所有 500 异常响应，统一转为 HTTP 200 + body {code,msg} 标准错误返回
(2) 认证失败 → 业务码 4001（前端据此跳转登录）
(3) 路由 404 → 业务码 404，msg "404错误：您访问的地址不存在"
(4) 参数校验失败 → 业务码 4000，msg 格式对齐 DRF："字段名: 第一个错误信息"
"""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class APIException(Exception):
    """
    通用异常:(1)用于接口请求时抛出, 此时code会被当做标准返回的code, message会被当做标准返回的msg
    """

    def __init__(self, code=201, message='API异常', args=('API异常',)):
        self.args = args
        self.code = code
        self.message = message

    def __str__(self):
        return self.message


class AuthenticationError(APIException):
    """认证失败（对应 DRF AuthenticationFailed/NotAuthenticated → 业务码 4001）"""

    def __init__(self, message='身份认证已过期'):
        super().__init__(code=4001, message=message, args=(message,))


class PermissionDeniedError(APIException):
    """权限不足（对应 DRF PermissionDenied → 业务码 4000）"""

    def __init__(self, message='您没有执行该操作的权限'):
        super().__init__(code=4000, message=message, args=(message,))


def _error_json(msg, code=4000, status=200) -> JSONResponse:
    # 对齐 DJ：异常响应同样经过 LoopbackRewriteJSONRenderer 渲染（msg 原样输出可能含 URL）
    from utils.renderers import rewrite_loopback
    content = {"code": code, "data": None, "msg": msg}
    rewrite_loopback(content)
    return JSONResponse(content=content, status_code=status)


def drf_validation_msg(field: str, text: str, code: str = 'unique') -> str:
    """对齐 DRF ValidationError + DJ CustomExceptionHandler 的 msg：
    DJ handler 对 ValidationError 恒走 except 分支 → msg = str(ex.detail)，
    即 ErrorDetail 字典的 repr（如 "{'key': [ErrorDetail(string='...', code='unique')]}"），业务码恒 4000"""
    return "{%r: [ErrorDetail(string=%r, code=%r)]}" % (field, text, code)


def _format_validation_msg(exc: RequestValidationError) -> str:
    """把 FastAPI 校验错误转成 DRF 风格的 "字段名: 错误信息" 格式"""
    try:
        first = exc.errors()[0]
        loc = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path", "header", "cookie")]
        field = ".".join(loc) if loc else "non_field_errors"
        return f"{field}: {first.get('msg')}"
    except Exception:
        return "请求参数校验失败"


def register_exception_handlers(app: FastAPI):
    """在 app 上注册全局异常处理器（统一转为标准错误响应，HTTP 状态码恒 200）
    与 Django 版 CustomExceptionHandler 对齐：
    (1) 自定义 APIException 一律 code=4000（Django 版 handler 从不读取 exc.code）
    (2) AuthenticationError → 4001；PermissionDeniedError → 4000
    (3) 数据库唯一冲突 → "数据有重复，请检查后重试:..."（MySQL 1062 检测逻辑对齐）
    """

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        # 对齐 Django：DRF AuthenticationFailed/NotAuthenticated → 4001；
        # 其余（含自定义 APIException，Django 版 handler 从不读取 exc.code）→ 4000
        if isinstance(exc, AuthenticationError):
            return _error_json(msg=exc.message, code=4001)
        return _error_json(msg=exc.message, code=4000)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # 对齐 Django Http404 → 业务码 404；其余 HTTP 异常 → 业务码 4000
        if exc.status_code == 404:
            return _error_json(msg="404错误：您访问的地址不存在", code=404)
        return _error_json(msg=str(exc.detail), code=4000)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _error_json(msg=_format_validation_msg(exc), code=4000)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # IntegrityError 对齐 Django：MySQL 1062 → "数据有重复，请检查后重试:..."，其余原样输出
        msg = str(exc)
        if exc.__class__.__name__ == "IntegrityError" or "IntegrityError" in msg[:60]:
            res = msg.split(', ')
            if res[0] == '(1062':
                msg = "数据有重复，请检查后重试:%s" % msg
        logger.error(traceback.format_exc())
        return _error_json(msg=msg, code=4000)
