# -*- coding: utf-8 -*-
"""
@Remark: 自定义文件上传（对应 Django utils/file_upload.py 的 ImageUpload）
说明：
(1) 校验链与 Django 版一致：content_type 须以 image/ 开头、扩展名白名单、单文件 ≤50MB
(2) 存储路径：MEDIA_ROOT/<dirs>/<%Y-%m-%d>/<重命名文件>，目录不存在自动创建
    （Django 版经 default_storage.save 落到本地文件系统，此处直接写文件，行为一致）
(3) 返回 URL：DOMAIN_HOST + MEDIA_URL + 相对路径（对齐 Django 拼接方式）
"""
import datetime
import os

from application import settings
from utils.common import renameuploadimg

# 支持的图片格式
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def ImageUpload(images, paramsname: str, dirs: str) -> dict:
    """
    图片上传功能
    参数:
        images: 已解析的上传文件列表，元素为 (filename, content_type, bytes) 三元组
        paramsname: formData 中提交数据的名称，如：file（FastAPI 版用于错误提示语义对齐）
        dirs: 要上传到的目录
    返回:
        包含状态码、消息和图片URL列表的字典 {'code', 'msg', 'img'}
    """
    msg = {
        'code': 400,
        'msg': '',
        'img': []
    }

    # 验证上传文件是否存在
    if not images:
        msg['msg'] = "上传的图片不能为空"
        return msg

    notimg_files = []
    img_urls = []

    try:
        for filename, content_type, data in images:
            # 验证文件类型
            if not (content_type or "").startswith('image/'):
                notimg_files.append(filename)
                continue

            # 验证文件扩展名
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                notimg_files.append(filename)
                continue

            # 验证文件大小
            if len(data) > MAX_FILE_SIZE:
                msg['msg'] = f"图片 {filename} 大小不能超过50M"
                return msg

            # 生成存储路径并保存
            curr_time = datetime.datetime.now()
            time_path = curr_time.strftime("%Y-%m-%d")
            new_filename = renameuploadimg(filename)
            relative_path = os.path.join(dirs, time_path, new_filename)

            full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(data)

            # 构建完整的URL（Django default_storage 返回 \ 分隔的 win 路径，统一为 /）
            file_path = relative_path.replace("\\", "/")
            web_img_url = f"{settings.DOMAIN_HOST}{settings.MEDIA_URL}{file_path}"
            img_urls.append(web_img_url)

        # 处理非图片文件提示
        if notimg_files:
            sample_files = ', '.join(notimg_files[:5])
            if len(notimg_files) > 5:
                sample_files += f" 等{len(notimg_files)}个文件"
            msg['msg'] = f"以下文件不是有效的图片格式: {sample_files}"
            return msg

        # 成功返回
        msg.update({
            'code': 200,
            'msg': '上传成功',
            'img': img_urls
        })

    except IOError as e:
        msg['msg'] = f"文件存储错误: {str(e)}"
    except Exception as e:
        msg['msg'] = f"图片上传失败: {str(e)}"

    return msg
