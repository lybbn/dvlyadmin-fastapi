# -*- coding: utf-8 -*-
"""
@Remark: 管理后台登录视图（对应 Django mysystem/views/login.py）
接口：GET /api/captcha/  POST /api/token/  POST /api/token/refresh/
JWT 与 Django simplejwt 完全互通；验证码与 django-simple-captcha 共用 captcha_captchastore 表
"""
import base64
import random
import uuid
from datetime import datetime, timedelta
from io import BytesIO

from fastapi import APIRouter, Body, Depends, Request
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from application.database import get_db
from config import IS_SINGLE_TOKEN
from mysystem.models import CaptchaStore, Users
from mysystem.views.system_config import getSystemConfig
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.request_util import save_login_log
from utils.security import TokenError, check_password, create_access_and_refresh, rotate_refresh_token

login_router = APIRouter()

# 对齐 Django settings 的验证码配置（CAPTCHA_IMAGE_SIZE/CAPTCHA_FOREGROUND_COLOR 等）
CAPTCHA_IMAGE_SIZE = (160, 60)
CAPTCHA_FOREGROUND_COLOR = '#3A7BFF'
CAPTCHA_BACKGROUND_COLOR = '#FFFFFF'


def _generate_math_challenge():
    """
    加减乘除验证码（对齐 captcha.helpers.math_challenge）
    challenge 形如 "5+3="，response 为结果字符串
    """
    operators = ("+", "*", "-")
    operands = (random.randint(1, 10), random.randint(1, 10))
    operator = random.choice(operators)
    if operands[0] < operands[1] and "-" == operator:
        operands = (operands[1], operands[0])
    challenge = "%d%s%d" % (operands[0], operator, operands[1])
    result = operands[0] + operands[1] if operator == "+" else \
        operands[0] * operands[1] if operator == "*" else operands[0] - operands[1]
    return challenge + "=", str(result)


def _load_captcha_font(size: int) -> ImageFont.ImageFont:
    """加载验证码字体（Windows 常见字体 → Pillow 默认字体兜底）"""
    for font_path in (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1 支持矢量默认字体
    except TypeError:
        return ImageFont.load_default()


def _render_captcha_image(challenge: str) -> bytes:
    """绘制验证码 PNG（白底 + 前景算式 + 随机噪声弧线，对齐 noise_arcs）"""
    width, height = CAPTCHA_IMAGE_SIZE
    img = Image.new("RGB", (width, height), CAPTCHA_BACKGROUND_COLOR)
    draw = ImageDraw.Draw(img)
    font = _load_captcha_font(42)

    # 文字绘制（算式整体居中）
    try:
        bbox = draw.textbbox((0, 0), challenge, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = len(challenge) * 24, 42
    draw.text(((width - text_w) / 2, (height - text_h) / 2 - 4),
              challenge, font=font, fill=CAPTCHA_FOREGROUND_COLOR)

    # 噪声弧线（对齐 captcha.helpers.noise_arcs）
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.arc([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], 0, 360,
                 fill=CAPTCHA_FOREGROUND_COLOR)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@login_router.get("/captcha/")
def captcha_view(db: Session = Depends(get_db)):
    """获取图片验证码（对应 CaptchaView，公开接口）"""
    challenge, response = _generate_math_challenge()
    # 40 位随机串（对齐 simple-captcha get_random_string(40)）
    hashkey = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    store = CaptchaStore(challenge=challenge, response=response, hashkey=hashkey,
                         expiration=datetime.now() + timedelta(minutes=1))
    db.add(store)
    db.commit()
    db.refresh(store)

    image_bytes = _render_captcha_image(challenge)
    image_base = base64.b64encode(image_bytes)
    json_data = {"key": store.id, "image_base": "data:image/png;base64," + image_base.decode('utf-8')}
    return DetailResponse(data=json_data)


@login_router.post("/token/")
def login_view(request: Request, db: Session = Depends(get_db), body: dict = Body(default={})):
    """登录接口（对应 LoginView，公开接口）"""
    username = body.get('username', None)
    password = body.get('password', None)
    captchaKey = body.get('captchaKey', None)
    captcha = body.get('captcha', None)

    open_capche = True
    capche_config = getSystemConfig(db, key="base.loginCaptcha", group=False)
    if capche_config:
        open_capche = capche_config.get("loginCaptcha", True)

    if open_capche:
        image_code = None
        if captchaKey is not None and str(captchaKey).isdigit():
            image_code = db.execute(
                select(CaptchaStore).where(CaptchaStore.id == int(captchaKey))
            ).scalars().first()
        five_minute_ago = datetime.now() - timedelta(hours=0, minutes=5, seconds=0)
        if image_code and five_minute_ago > image_code.expiration:
            _delete_expire_captcha(db)
            msg = "验证码过期"
            save_login_log(db, request, body, status=False, msg=msg)
            return ErrorResponse(msg=msg)
        else:
            if image_code and (image_code.response == captcha or image_code.challenge == captcha):
                if image_code:
                    db.delete(image_code)
                    db.commit()
            else:
                _delete_expire_captcha(db)
                msg = "图片验证码错误"
                save_login_log(db, request, body, status=False, msg=msg)
                return ErrorResponse(msg=msg)

    user = db.execute(
        select(Users).where(Users.username == username)
    ).scalars().first()

    if not user:
        return ErrorResponse(msg="账号/密码错误")

    if user and not user.is_staff:  # 判断是否允许登录后台
        msg = "您没有权限登录后台"
        save_login_log(db, request, body, status=False, msg=msg, user=user)
        return ErrorResponse(msg=msg)

    if user and not user.is_active:
        msg = "该账号已被禁用"
        save_login_log(db, request, body, status=False, msg=msg, user=user)
        return ErrorResponse(msg=msg)

    from utils.security import check_password
    if user and user.password and check_password(password or "", user.password):
        data = create_access_and_refresh(user.id)
        msg = "登录成功"
        user.last_login = datetime.now()
        db.commit()
        save_login_log(db, request, body, status=True, msg=msg, user=user)
        # 缓存用户的jwt token（单点登录，IS_SINGLE_TOKEN 默认 False）
        if IS_SINGLE_TOKEN:
            _cache_single_token(user, data)
        return DetailResponse(data=data, msg=msg)
    else:
        msg = "账号/密码错误"
        save_login_log(db, request, body, status=False, msg=msg, user=user)
        return ErrorResponse(msg=msg)


@login_router.post("/token/refresh/")
def token_refresh_view(body: dict = Body(default={})):
    """
    刷新token（对应 simplejwt TokenRefreshView）
    返回体与 Django 版一致：直接 {"access": ..., "refresh": ...}（无标准包装）
    失败时：HTTP 200 + {"code":4001, "msg":"Token is invalid or expired"}
    （TokenViewBase 的 InvalidToken 经 CustomExceptionHandler 转为标准错误响应）
    """
    refresh = body.get("refresh")
    try:
        data = rotate_refresh_token(refresh or "")
    except TokenError:
        return ErrorResponse(msg="Token is invalid or expired", code=4001)
    from utils.jsonResponse import _json
    return _json(data)


def _delete_expire_captcha(db: Session):
    """删除过期验证码（对齐 LoginView.delete_expire_captcha）"""
    five_minute_ago = datetime.now() - timedelta(hours=0, minutes=5, seconds=0)
    db.execute(delete(CaptchaStore).where(CaptchaStore.expiration <= five_minute_ago))
    db.commit()


def _cache_single_token(user, data):
    """单点登录缓存（IS_SINGLE_TOKEN=True 时启用；阶段5接入统一缓存后实现）"""
    pass
