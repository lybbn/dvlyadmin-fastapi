# -*- coding: utf-8 -*-
"""
@Remark: 前端集成部署与图片上传（对应 Django mysystem/views/frontend.py）
- sys_image_upload: 图片上传（POST multipart，字段名 file，可多文件；仅需登录无需接口权限）
- h5web: uniapp h5 页面部署（FRONTEND_ROOT/h5/index.html；对齐 Django render 模板行为）
  路由注册对齐 Django：sys_image_upload → mysystem/urls.py，h5 → application/urls.py
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from application import settings
from mysystem.models import Users
from utils.file_upload import ImageUpload
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.permission import get_current_user

frontend_router = APIRouter()


@frontend_router.post("/sys_image_upload/")
async def sys_image_upload(request: Request, user: Users = Depends(get_current_user)):
    """【功能描述】图片上传功能API</br>【参数说明】无，需要登录携带token后才能调用"""
    # 对齐 Django request.FILES.getlist("file")：同名字段可提交多个文件
    form = await request.form()
    images = []
    for value in form.getlist("file"):
        data = await value.read()
        images.append((value.filename, value.content_type, data))
    result = ImageUpload(images, "file", "platform")
    if result['code'] == 200:
        return DetailResponse(data=result['img'], msg=result['msg'])
    else:
        return ErrorResponse(msg=result['msg'])


def h5web():
    """h5端页面（对齐 Django render(request, "h5/index.html")；模板缺失时抛错与 Django 一致）"""
    index = settings.FRONTEND_ROOT / "h5" / "index.html"
    if not index.exists():
        raise RuntimeError("h5/index.html 模板不存在（对齐 Django TemplateDoesNotExist）")
    return HTMLResponse(index.read_text(encoding="utf-8"))
