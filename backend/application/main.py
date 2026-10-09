# -*- coding: utf-8 -*-
"""
@Remark: FastAPI 应用入口（对应 Django application/asgi.py + manage.py runserver）
启动方式：python run.py（端口 8000，与 Django 版一致，前端零改动切换；两端不可同时运行）
说明：
(1) CORS 对齐 django-cors-headers 的 CORS_ORIGIN_ALLOW_ALL=True
(2) X-Frame-Options/COOP 响应头对齐 Django 安全中间件
(3) OpenAPI 文档路径对齐 Django drf-spectacular：
    - JSON:  /api/schema/lyjson
    - UI:    /api/schema/swagger-ui
    （Django 版该 JSON 需 JWT 认证访问，FastAPI 此处为开发工具页面，不做认证门槛）
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from application import settings
from application.urls import api_router
from utils.exception import register_exception_handlers

logger = logging.getLogger(__name__)


def _check_database():
    """启动时探测数据库连通性（仅记录日志，不阻断启动）"""
    from application.database import engine
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        logger.info("数据库连接成功：%s", engine.url.render_as_string(hide_password=True))
    except Exception as exc:
        logger.error("数据库连接失败：%s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 对齐 Django settings 导入期自动创建 media/logs 目录的行为
    settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.STATIC_ROOT.mkdir(parents=True, exist_ok=True)
    settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # WebSocket 推送需要主事件循环引用（同步线程池线程跨线程调度，对齐 async_to_sync）
    import asyncio
    from utils.ws import manager
    manager.set_loop(asyncio.get_running_loop())
    _check_database()
    yield


def create_app() -> FastAPI:
    settings.setup_logging()

    app = FastAPI(
        title="dvlyadmin-mini FastAPI API",
        description="dvlyadmin-mini全栈快速web开发框架的API文档（FastAPI 复刻版）",
        version="1.0.0",
        # 固定 False：Starlette 在 debug=True 时让 ServerErrorMiddleware 优先输出
        # 500 + 明文堆栈（绕过下方注册的 Exception 处理器），与 Django 统一返回
        # {"code":4000,...} 的行为不一致，且有堆栈泄露风险（见 utils/exception.py）
        debug=False,
        lifespan=lifespan,
        # 文档路径对齐 Django drf-spectacular
        openapi_url="/api/schema/lyjson" if settings.DEBUG else None,
        docs_url="/api/schema/swagger-ui" if settings.DEBUG else None,
        redoc_url="/api/schema/redoc" if settings.DEBUG else None,
    )

    app.include_router(api_router)
    # WebSocket 消息推送（对齐 channels websocket_urlpatterns：/ws/msg/）
    from utils.ws import ws_router
    app.include_router(ws_router)
    register_exception_handlers(app)

    # 日志/节流中间件（对齐 Django MIDDLEWARE 的 ApiLoggingMiddleware；
    # 必须在 CORS 之前注册 → CORS 最外层保证异常/节流响应也带跨域头）
    from utils.middleware import ApiLoggingMiddleware
    app.add_middleware(ApiLoggingMiddleware)

    # 安全响应头（对齐 XFrameOptionsMiddleware 与 SECURE_CROSS_ORIGIN_OPENER_POLICY）
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "None")
        return response

    # CORS 必须最后注册（最外层），保证异常响应也带跨域头
    # 对齐 CORS_ALLOW_ALL_ORIGINS=True + CORS_EXPOSE_HEADERS=['Content-Disposition']
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # allow_origins=["*"] 时不可开启（与 Django 行为一致）
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    return app


app = create_app()
