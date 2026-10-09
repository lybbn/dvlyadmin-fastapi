# -*- coding: utf-8 -*-
"""
@Remark: 接口节流（对应 DRF DEFAULT_THROTTLE_CLASSES: AnonRateThrottle + UserRateThrottle）
与 DRF SimpleRateThrottle 行为对齐的关键点：
(1) 固定窗口计数：窗口首请求起算 duration 秒，窗口内计数超限即拒绝
(2) AnonRateThrottle 只作用于未认证请求，ident = 客户端 IP（X-Forwarded-For 取第一个）
(3) UserRateThrottle 只作用于认证请求，ident = user pk（此处用 token 中的 user_id，免查库）
(4) 超限 → DRF Throttled 异常 → 项目 CustomExceptionHandler → HTTP 200 + code 4000，
    msg 为 DRF 默认英文 detail："Request was throttled. Expected available in N seconds."
"""
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from config import FRONTEND_API_LIST
from utils.security import TokenError, decode_token

# 简单内存计数（对齐 InMemory 缓存后端；单进程部署与 DRF 行为一致）
_lock = threading.Lock()
_history = {}  # {ident: (count, window_start)}


def _parse_rate(rate: str):
    """'60/minute' → (60, 60)"""
    num, _, period = rate.partition("/")
    duration = {"s": 1, "second": 1, "m": 60, "minute": 60, "h": 3600, "hour": 3600,
                "d": 86400, "day": 86400}.get(period.strip(), 60)
    return int(num), duration


def _get_ident(request: Request) -> str:
    """对齐 DRF BaseThrottle.get_ident：X-Forwarded-For 取第一个 IP"""
    xff = request.headers.get("X-Forwarded-For", "")
    ip = xff.split(",")[0].strip() if xff else ""
    if not ip and request.client:
        ip = request.client.host or ""
    return ip


def _allow_request(key: str, rate: str) -> tuple:
    """固定窗口计数检查。返回 (是否允许, 还需等待秒数)"""
    num_requests, duration = _parse_rate(rate)
    now = time.time()
    with _lock:
        count, start = _history.get(key, (0, now))
        if now - start >= duration:
            # 窗口过期，重新起算（对齐 DRF cache.incr 超时重置行为）
            _history[key] = (1, now)
            return True, 0
        if count >= num_requests:
            return False, int(duration - (now - start)) + 1
        _history[key] = (count + 1, start)
        return True, 0


def check_throttle(request: Request, anon_rate: str, user_rate: str):
    """
    对齐 AnonRateThrottle + UserRateThrottle 组合：认证用户走 user 频率，未认证走 anon 频率。
    超限直接返回 JSONResponse（middleware 层抛异常不会被 exception handler 捕获）
    """
    path = request.url.path
    # DRF 节流只作用于 APIView；此处等价为仅 /api/ 接口路由（静态文件/页面/WS 不节流）
    if not path.startswith("/api/"):
        return None

    user_id = None
    header = request.headers.get('Authorization', '')
    parts = header.split()
    if len(parts) == 2 and parts[0] == 'JWT':
        try:
            user_id = decode_token(parts[1], expected_type="access").get("user_id")
        except TokenError:
            user_id = None

    if user_id:
        allowed, wait = _allow_request(f"throttle_user_{user_id}", user_rate)
    else:
        allowed, wait = _allow_request(f"throttle_anon_{_get_ident(request)}", anon_rate)
    if allowed:
        return None
    # 对齐 DRF Throttled 默认 detail（项目自定义 handler 原样输出 str(detail) → code 4000）
    msg = f"Request was throttled. Expected available in {wait} second."
    return JSONResponse(content={"code": 4000, "data": None, "msg": msg}, status_code=200)
