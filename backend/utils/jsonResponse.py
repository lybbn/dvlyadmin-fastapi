# -*- coding: utf-8 -*-
"""
@Remark: 自定义的JsonResponse文件（对应 Django utils/jsonResponse.py）
与 DRF 版行为完全对齐：
(1) HTTP 状态码恒为 200（业务码放 body.code），前端只认 body.code
(2) SuccessResponse: {"code":2000,"data":{"page","limit","total","data"},"msg"}
(3) DetailResponse:  {"code":2000,"data":...,"msg"}
(4) ErrorResponse:   {"code":400(默认),"data":...,"msg"}，可用 status 参数改 HTTP 状态码
"""
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from utils.renderers import rewrite_loopback


def _json(content: Any, status_code: int = 200, headers: Optional[dict] = None) -> JSONResponse:
    # 出栈改写回环地址（对齐 DJ LoopbackRewriteJSONRenderer 全局渲染器）
    if isinstance(content, dict):
        rewrite_loopback(content)
    # jsonable_encoder 统一处理 datetime 等不可直接序列化的类型
    return JSONResponse(
        content=jsonable_encoder(content),
        status_code=status_code,
        headers=headers,
    )


def SuccessResponse(data=None, msg: str = 'success', page: int = 1, limit: int = 1,
                    total: int = 1, code: int = 2000, headers: Optional[dict] = None) -> JSONResponse:
    """
    标准响应成功的返回, SuccessResponse(data)或者SuccessResponse(data=data)
    (1)默认code返回2000, 不支持指定其他返回码
    (2)不含分页数据时 total 归零（与 DRF 版 `if not data: total = 0` 一致）
    """
    if not data:
        total = 0
    std_data = {
        "code": code,
        "data": {
            "page": page,
            "limit": limit,
            "total": total,
            "data": data,
        },
        "msg": msg,
    }
    return _json(std_data, headers=headers)


def DetailResponse(data=None, msg: str = 'success', code: int = 2000,
                   headers: Optional[dict] = None) -> JSONResponse:
    """
    不包含分页信息的接口返回,主要用于单条数据查询
    (1)默认code返回2000, 不支持指定其他返回码
    """
    std_data = {
        "code": code,
        "data": data,
        "msg": msg,
    }
    return _json(std_data, headers=headers)


def ErrorResponse(data=None, msg: str = 'error', code: int = 400, status: Optional[int] = None,
                  headers: Optional[dict] = None) -> JSONResponse:
    """
    标准响应错误的返回,ErrorResponse(msg='xxx')
    (1)默认错误码返回400, 也可以指定其他返回码:ErrorResponse(code=xxx)
    (2)默认 HTTP 状态码仍为 200（与 DRF Response status=None 行为一致）
    """
    std_data = {
        "code": code,
        "data": data,
        "msg": msg,
    }
    return _json(std_data, status_code=status or 200, headers=headers)
