# -*- coding: utf-8 -*-
"""
@Remark: 总路由注册（对应 Django application/urls.py）
路由路径与 Django 版完全一致（含结尾斜杠）：
- 阶段1 认证链: /api/token/  /api/token/refresh/  /api/captcha/
                /api/system/getconfig/  /api/system/user/user_info|change_password|change_avatar/
- 阶段2+3 业务接口: /api/system/...（mysystem 全部视图集）
- 阶段4 附件与页面: /media/  /static/  /h5/  /favicon.ico  /（lyadmin 集成部署页）
"""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from application import settings

api_router = APIRouter()

# ---------- 阶段1 认证链 ----------
from mysystem.views.login import login_router
from mysystem.views.system_config import system_config_router
from mysystem.views.user import user_router

api_router.include_router(login_router, prefix="/api")                      # /api/token/ 等
api_router.include_router(system_config_router, prefix="/api/system")       # /api/system/getconfig/
api_router.include_router(user_router, prefix="/api/system/user")           # /api/system/user/user_info/ 等

# ---------- 阶段2 系统管理 CRUD ----------
from mysystem.urls import system_router
api_router.include_router(system_router, prefix="/api/system")              # /api/system/dept/...

# ---------- 阶段4 静态/媒体/页面（对齐 application/urls.py 前 3 行与尾部 4 行） ----------
from utils.streamingmedia_response import serve_static_file, streamingmedia_serve
from mysystem.views.frontend import h5web


@api_router.get("/static/{path:path}")
def static_serve(request: Request, path: str):
    """处理静态文件（对齐 django.views.static.serve）"""
    return serve_static_file(request, path, settings.STATIC_ROOT)


@api_router.get("/media/{path:path}")
def media_serve(request: Request, path: str):
    """处理媒体文件（对齐 streamingmedia_serve：视频 Range 流式/304/gzip/缓存头）"""
    return streamingmedia_serve(request, path, settings.MEDIA_ROOT)


@api_router.get("/favicon.ico")
def favicon():
    # 对齐 RedirectView.as_view(url='static/favicon.ico')（默认 302 临时重定向）
    return RedirectResponse(url="/static/favicon.ico", status_code=302)


@api_router.get("/", include_in_schema=False)
def index():
    """后台管理默认页面（对齐 TemplateView template_name="lyadmin/index.html"）"""
    index_file = settings.FRONTEND_ROOT / "lyadmin" / "index.html"
    if not index_file.exists():
        return Response(content="lyadmin/index.html 不存在", status_code=404, media_type="text/plain")
    return FileResponse(index_file, media_type="text/html")


# h5 端页面注册（对齐 path('h5/', h5web)）
api_router.get("/h5/", include_in_schema=False)(h5web)
