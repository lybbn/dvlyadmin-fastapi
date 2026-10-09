# -*- coding: utf-8 -*-
"""
@Remark: 快速生成用户 JWT token（对应 Django 版: python manage.py generate_token 用户ID）
用法: python run.py generate_token 用户ID
说明：payload 与登录接口同源（utils.security.create_access_and_refresh），
      签发结果与 Django simplejwt 完全互通（同一 SECRET_KEY、同一 HS256）
"""
from application.database import SessionLocal
from commands.base import ok
from mysystem.models import Users
from utils.security import create_access_and_refresh


def add_arguments(parser):
    parser.add_argument("userid", nargs="*", type=str, help="用户ID")


def handle(args):
    userid_list = args.userid
    if not userid_list:
        ok("请输入要生成token的用户ID如：python run.py generate_token 用户ID")
        return 0

    db = SessionLocal()
    try:
        user = db.get(Users, userid_list[0])
    finally:
        db.close()

    if not user:
        ok("用户不存在")
        return 0

    tokens = create_access_and_refresh(user.id)
    userinfo = {
        "identity": user.identity,
        "userId": user.id,
        "refresh": tokens["refresh"],
        "access": tokens["access"],
    }
    print(userinfo)
    return 0