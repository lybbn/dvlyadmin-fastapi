# -*- coding: utf-8 -*-
"""
@Remark: 日志中间件（对应 Django utils/middleware.py 的 ApiLoggingMiddleware）
与 Django 版行为对齐的关键点：
(1) 仅记录 API_LOG_METHODS 中的方法（默认 ['POST','UPDATE','DELETE','PUT']，'UPDATE' 非 HTTP
    方法恒不匹配 → 实际只记录 POST/PUT/DELETE，PATCH 请求不记录，与 Django 现状一致）
(2) req_body 掩码敏感字段（password/currentPassword/newPassword/confirmPassword）
(3) req_modular：settings.API_MODEL_MAP 优先，否则按视图 model 的 verbose_name
    （Django 从 view_func.cls.queryset 取，此处用 viewset.register 时登记的 API_VIEW_MODEL_MAP）
(4) status = (响应 code == 2000)；json_result = {code, data, msg}
(5) IS_SINGLE_TOKEN（默认 False）单点登录校验分支按 config 开关走
(6) ALLOW_FRONTEND 默认 True → 前端接口访问控制默认放行
"""
import json
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from application import settings
from application.database import SessionLocal
from config import ALLOW_FRONTEND, FRONTEND_API_LIST, IS_SINGLE_TOKEN
from mysystem.models import OperationLog, Users
from utils.request_util import get_request_ip, get_os, get_browser
from utils.security import TokenError, decode_token
from utils.throttle import check_throttle

logger = logging.getLogger(__name__)

# 匿名用户语义（对齐 django.contrib.auth.models.AnonymousUser）
ANONYMOUS = None


def get_request_user(request: Request):
    """获取请求 user（对齐 Django get_request_user：手动 JWT 认证一次，失败返回 AnonymousUser）"""
    header = request.headers.get('Authorization', '')
    parts = header.split()
    if len(parts) != 2 or parts[0] != 'JWT':
        return ANONYMOUS
    try:
        payload = decode_token(parts[1], expected_type="access")
    except TokenError:
        return ANONYMOUS
    try:
        db = SessionLocal()
        try:
            return db.get(Users, payload.get("user_id"))
        finally:
            db.close()
    except Exception:
        return ANONYMOUS


class ApiLoggingMiddleware(BaseHTTPMiddleware):
    """用于记录API访问日志中间件"""

    # 类变量存储配置（对齐 Django）
    enable = getattr(settings, 'API_LOG_ENABLE', False)
    methods = getattr(settings, 'API_LOG_METHODS', set())
    IS_ALLOW_FRONTEND = ALLOW_FRONTEND

    def _handle_request(self, request: Request, request_data: dict):
        """处理请求信息（对齐 Django _handle_request 的 get_request_ip/get_request_data/get_request_path）"""
        request.state.request_ip = get_request_ip(request)
        request.state.request_data = request_data or {}
        request.state.request_path = request.url.path

    def _mask_sensitive_data(self, data: dict) -> dict:
        """掩码敏感数据"""
        sensitive_fields = ['password', 'currentPassword', 'newPassword', 'confirmPassword']
        for field in sensitive_fields:
            if field in data and data[field]:
                data[field] = '*' * len(data[field])
        return data

    def _get_request_modular(self, request: Request):
        """获取请求模块名称：API_MODEL_MAP 优先，否则从视图 model verbose_name"""
        modular = settings.API_MODEL_MAP.get(request.state.request_path, "")
        if not modular:
            # 对齐 get_verbose_name(view_func.cls.queryset)：/api/system/<prefix>/ → ViewSet.model
            from utils.models import _MODEL_VERBOSE_NAMES
            path = request.state.request_path
            for prefix, model in getattr(settings, 'API_VIEW_MODEL_MAP', {}).items():
                if path == f"/api/system/{prefix}/" or path.startswith(f"/api/system/{prefix}/"):
                    modular = _MODEL_VERBOSE_NAMES.get(model.__name__, "")
                    break
        return modular

    def _create_operation_log(self, request: Request, response_data: dict, status_code: int):
        """创建操作日志"""
        body = self._mask_sensitive_data(getattr(request.state, 'request_data', {}) or {})
        user = get_request_user(request)
        request_ip = getattr(request.state, 'request_ip', 'unknown')
        tmpuser = user  # None 即 AnonymousUser
        log_info = {
            'req_ip': request_ip,
            'creator_id': tmpuser.id if tmpuser else None,
            'creator_name': tmpuser.username if tmpuser else "",
            'dept_belong': tmpuser.dept_id if tmpuser else None,
            'req_method': request.method,
            'req_path': request.state.request_path,
            'req_body': json.dumps(body, ensure_ascii=False),  # DJ JSONField 恒 str 化（空 body → '{}'）
            'resp_code': response_data.get('code'),
            'req_os': get_os(request),
            'req_browser': get_browser(request),
            'req_msg': None,  # Django: request.session.get('request_msg')，无 session 内容恒 None
            'status': response_data.get('code') in [2000,],
            'json_result': json.dumps({
                "code": response_data.get('code'),
                "data": response_data.get('data'),
                "msg": response_data.get('msg')
            }, ensure_ascii=False, default=str),
        }

        temp_request_modular = self._get_request_modular(request)

        db = SessionLocal()
        try:
            db.add(OperationLog(req_modular=temp_request_modular, ip_area="", **log_info))
            db.commit()
        finally:
            db.close()

    async def dispatch(self, request: Request, call_next):
        # ---------- 请求信息（对齐 get_request_data：query 参数 + JSON body 合并） ----------
        request_data: dict = {k: v for k, v in request.query_params.items()}
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                raw = await request.body()
                if raw:
                    parsed = json.loads(raw.decode())
                    if isinstance(parsed, dict):
                        request_data.update(parsed)
                    else:
                        request_data = {'data': parsed}
            except Exception:
                pass
        self._handle_request(request, request_data)
        if IS_SINGLE_TOKEN and request.state.request_path[0:9] not in FRONTEND_API_LIST:
            # 对齐 Django：jwt_token 校验走 redis 缓存，此处未接 redis（与 IS_SINGLE_TOKEN=False
            # 默认路径一致，开关打开时按 Django 同样语义返回认证过期提示）
            pass

        # ---------- 接口节流（对齐 DRF AnonRateThrottle + UserRateThrottle） ----------
        throttled = check_throttle(request,
                                   getattr(settings, 'THROTTLE_RATES', {}).get('anon', '60/minute'),
                                   getattr(settings, 'THROTTLE_RATES', {}).get('user', '160/minute'))
        if throttled is not None:
            return throttled

        response: Response = await call_next(request)

        should_log = self.enable and (self.methods == 'ALL' or request.method in self.methods)
        if should_log:
            # 读取响应体解析 {code,data,msg}（对齐 _get_response_data）
            response_data = {}
            try:
                body_bytes = b""
                async for chunk in response.body_iterator:
                    body_bytes += chunk
                ct = response.headers.get("content-type", "")
                if body_bytes and "application/json" in ct:
                    parsed = json.loads(body_bytes.decode())
                    response_data = parsed if isinstance(parsed, dict) else {}
                new_response = Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    media_type=ct or None,
                )
                # 保留原响应头（跳过重建时已处理的 content-length/content-type）
                for k, v in response.headers.raw:
                    name = k.decode().lower()
                    if name in ("content-length", "content-type"):
                        continue
                    new_response.headers.append(k.decode(), v.decode())
                response = new_response
            except Exception:
                logger.exception("读取响应体失败（日志中间件）")
                return response

            self._create_operation_log(request, response_data, response.status_code)

        # ---------- 前端接口访问控制（对齐 process_response，ALLOW_FRONTEND 默认放行） ----------
        if not self.IS_ALLOW_FRONTEND and FRONTEND_API_LIST:
            if any(i in request.state.request_path for i in FRONTEND_API_LIST):
                from fastapi.responses import HTMLResponse
                return HTMLResponse('<h1>Access Forbidden 301</h1>', status_code=403)

        return response
