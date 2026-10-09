# -*- coding: utf-8 -*-
"""
@Remark: 自定义分页（对应 Django utils/pagination.py 的 CustomPagination）
与 DRF 版行为对齐：
(1) page_size=10，limit 查询参数控制每页条数，最大 999
(2) 页码越界时不报错，返回 data=[] + msg="暂无数据" + total=0（原版 InvalidPage 分支）
(3) 响应结构 {"code":2000,"msg":"success","data":{"page","limit","total","data"}}
"""
from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def get_page_size(request: Request, page_size: int = 10, max_page_size: int = 999) -> int:
    """对齐 PageNumberPagination.get_page_size：limit 参数，默认10，最大999"""
    try:
        limit = int(request.query_params.get("limit", page_size))
    except (TypeError, ValueError):
        limit = page_size
    if limit <= 0:
        limit = page_size
    return min(limit, max_page_size)


def get_page_number(request: Request) -> int:
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    return page if page > 0 else 1


def paginate_queryset(db: Session, request: Request, query, page_size: int = 10,
                      max_page_size: int = 999):
    """
    分页执行器：返回 (items, total, page, limit)
    total 为过滤后 queryset 的总数（对齐 Django Paginator.count）
    页码越界 → items=[]（由 paginate_response 输出 暂无数据/total=0）
    """
    limit = get_page_size(request, page_size, max_page_size)
    page = get_page_number(request)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    items = db.execute(query.limit(limit).offset((page - 1) * limit)).scalars().all()
    return list(items), total, page, limit


def paginate_response(request: Request, data: list, total: int, page: int, limit: int):
    """
    对齐 CustomPagination.get_paginated_response：
    无数据时 msg="暂无数据"、data=[]、total=0
    """
    from utils.jsonResponse import _json
    if not data:
        res = {"page": page, "total": 0, "limit": limit, "data": []}
        return _json({"code": 2000, "msg": "暂无数据", "data": res})
    res = {"page": page, "total": total, "limit": limit, "data": data}
    return _json({"code": 2000, "msg": "success", "data": res})
