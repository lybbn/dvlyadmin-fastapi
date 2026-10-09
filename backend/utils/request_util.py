# -*- coding: utf-8 -*-
"""
@Remark: Request 工具类（对应 Django utils/request_util.py）
"""
from user_agents import parse as ua_parse

from mysystem.models import LoginLog


def get_request_ip(request):
    """
    获取请求IP（对齐 Django 版：X-Forwarded-For 优先，取最后一个）
    :param request: starlette Request
    """
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[-1].strip()
        return ip
    client_host = getattr(request.client, 'host', None) if request.client else None
    return client_host or 'unknown'


def get_browser(request):
    """获取浏览器名"""
    browser = ""
    try:
        ua_string = request.headers.get('User-Agent', '')
        if ua_string:
            browser = ua_parse(ua_string).get_browser()
    except Exception:
        pass
    return browser


def get_os(request):
    """获取操作系统"""
    theos = ""
    try:
        ua_string = request.headers.get('User-Agent', '')
        if ua_string:
            theos = ua_parse(ua_string).get_os()
    except Exception:
        pass
    return theos


def save_login_log(db, request, body=None, status=True, msg="", user=None):
    """
    保存登录日志（对齐 Django utils/request_util.save_login_log）
    :param db: SQLAlchemy Session
    :param request: starlette Request
    :param body: 请求体 dict（取 username）
    :param status: 登录是否成功
    :param msg: 自定义内容
    :param user: 登录成功时的用户对象
    """
    body = body or {}
    user_id = user.id if user else None
    ip = get_request_ip(request)
    username = body.get('username', None)
    agent = ""
    try:
        agent = str(ua_parse(request.headers.get('User-Agent', '')))
    except Exception:
        pass
    creator_id = user_id
    dept_belong = user.dept_id if user else ''
    db.add(LoginLog(
        username=username,
        ip=ip,
        agent=agent,
        browser=get_browser(request),
        os=get_os(request),
        creator_id=creator_id,
        dept_belong=dept_belong,
        status=status,
        msg=msg,
    ))
    db.commit()
