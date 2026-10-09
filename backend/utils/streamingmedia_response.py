# -*- coding: utf-8 -*-
"""
@Remark: 静态/媒体文件服务（对应 Django utils/streamingmedia_response.py 与 django.views.static.serve）
说明（开发期文件服务，生产环境应由 nginx 承担）：
(1) /media/ → streamingmedia_serve：视频/音频 Range 分片流式（对齐 stream_video 10MB 分片）、
    If-Modified-Since 304、gzip 预压缩文件回退、Cache-Control 策略、apk 特殊 content-type
(2) /static/ → serve_static_file：django.views.static.serve 的精简复刻（安全路径 + 304）
"""
import mimetypes
import os
import re
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, Response, StreamingResponse

# Vite 构建产物的文件名包含 hash，可以设置长期缓存
# 匹配类似 app.abc123.js、index.def456.css 这种带 hash 的文件名
_hash_pattern = re.compile(r'\.[0-9a-f]{8,}\.')

# Range 分片大小（对齐 Django 版 stream_video：first_byte + 1024*1024*10）
_STREAM_CHUNK = 1024 * 1024 * 10


def _is_hashed_asset(filename):
    """判断静态资源文件名是否包含内容 hash（Vite/Rollup 产物特征）"""
    return bool(_hash_pattern.search(filename))


def _get_cache_control(path_str, is_hashed):
    """根据文件类型和是否带 hash 返回 Cache-Control 策略"""
    ext = os.path.splitext(path_str)[1].lower()
    # 带 hash 的 JS/CSS/SVG/字体文件 → 长期缓存（1年），内容变了 hash 会变
    if is_hashed and ext in ('.js', '.css', '.svg', '.woff', '.woff2', '.ttf', '.eot'):
        return 'public, max-age=31536000, immutable'
    # 图片资源 → 中期缓存（30天）
    if ext in ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.avif'):
        return 'public, max-age=2592000'
    # HTML 和其他 → 短期缓存（1小时），确保更新及时生效
    if ext in ('.html', '.htm'):
        return 'public, max-age=3600, must-revalidate'
    # 其他静态资源 → 1天缓存
    return 'public, max-age=86400'


def _safe_join(document_root, path: str) -> Path:
    """对齐 django.utils._os.safe_join：拼路径并校验不逃逸出根目录（Windows 需两侧 normcase）"""
    root = Path(document_root).resolve()
    full = (root / path).resolve()
    root_nc = os.path.normcase(str(root))
    full_nc = os.path.normcase(str(full))
    if full_nc.startswith(root_nc + os.sep) or full_nc == root_nc:
        return full
    raise PermissionError("非法路径访问")


def _not_found(path: str) -> Response:
    # 对齐 Django Http404 默认行为：HTTP 404 状态码 + 简短文本（非接口路由，不走 code 404 JSON 约定）
    return Response(content=f"“{path}” does not exist", status_code=404, media_type="text/plain")


def _was_modified_since(header=None, mtime=0, size=0) -> bool:
    """对齐 django.utils.http.was_modified_since / django.views.static 判断逻辑"""
    try:
        if header is None:
            raise ValueError
        matches = re.match(r"^([^;]+)(; length=([0-9]+))?$", header, re.IGNORECASE)
        header_mtime = parsedate_to_datetime(matches[1]).timestamp()
        header_len = matches.group(3)
        if header_len and int(header_len) != size:
            raise ValueError
        if int(mtime) > header_mtime:
            raise ValueError
    except (AttributeError, ValueError, OverflowError, TypeError):
        return True
    return False


def _file_iterator(path, offset=0, length=None, chunk_size=8192):
    """分片读取（对齐 file_iterator）"""
    with open(path, "rb") as f:
        f.seek(offset, os.SEEK_SET)
        remaining = length
        while True:
            bytes_length = chunk_size if remaining is None else min(remaining, chunk_size)
            data = f.read(bytes_length)
            if not data:
                break
            if remaining:
                remaining -= len(data)
            yield data


def _stream_video(request: Request, path, content_type) -> Response:
    """将视频文件以流媒体的方式响应（对齐 stream_video：Range → 206 分片）"""
    range_header = (request.headers.get("range") or "").strip()
    range_re = re.compile(r'bytes\s*=\s*(\d+)\s*-\s*(\d*)', re.I)
    range_match = range_re.match(range_header)
    size = os.path.getsize(path)
    if range_match:
        first_byte, last_byte = range_match.groups()
        first_byte = int(first_byte) if first_byte else 0
        last_byte = first_byte + _STREAM_CHUNK
        if last_byte >= size:
            last_byte = size - 1
        length = last_byte - first_byte + 1
        return StreamingResponse(
            _file_iterator(path, offset=first_byte, length=length),
            status_code=206, media_type=content_type,
            headers={
                "Content-Length": str(length),
                "Content-Range": f'bytes {first_byte}-{last_byte}/{size}',
                "Accept-Ranges": "bytes",
            })
    return FileResponse(path, media_type=content_type, headers={"Accept-Ranges": "bytes"})


def streamingmedia_serve(request: Request, path: str, document_root) -> Response:
    """媒体文件服务（对齐 Django streamingmedia_serve）"""
    path = os.path.normpath(path).lstrip("/").replace("\\", "/")
    try:
        fullpath = _safe_join(document_root, path)
    except (PermissionError, OSError, ValueError):
        return _not_found(path)
    if fullpath.is_dir():
        return Response(content="Directory indexes are not allowed here.", status_code=404,
                        media_type="text/plain")
    if not fullpath.exists():
        return _not_found(path)
    # Respect the If-Modified-Since header.
    statobj = fullpath.stat()
    if not _was_modified_since(request.headers.get("if-modified-since"),
                               statobj.st_mtime, statobj.st_size):
        return Response(status_code=304)
    content_type, encoding = mimetypes.guess_type(str(fullpath))
    content_type = content_type or 'application/octet-stream'
    if content_type in ['video/mp4', 'video/ogg', 'video/flv', 'video/avi', 'video/wmv', 'video/rmvb',
                        'audio/mp3', 'audio/x-m4a', 'audio/mpeg', 'audio/ogg']:
        return _stream_video(request, fullpath, content_type)
    elif fullpath.suffix in ['.apk']:  # 兼容小米的浏览器等迅雷下载内核无法下载问题
        return FileResponse(fullpath, media_type='application/vnd.android.package-archive',
                            headers={"Content-Length": str(statobj.st_size)})
    else:
        # 尝试返回 gzip 预压缩文件（构建时由 vite-plugin-compression 生成）
        accept_encoding = request.headers.get("accept-encoding", "")
        if 'gzip' in accept_encoding and fullpath.suffix in ('.js', '.css', '.svg', '.html', '.json', '.woff2', '.ttf'):
            gz_path = fullpath.with_suffix(fullpath.suffix + '.gz')
            if gz_path.exists():
                return FileResponse(gz_path, media_type=content_type, headers={
                    "Content-Encoding": "gzip",
                    "Content-Length": str(gz_path.stat().st_size),
                    "Vary": "Accept-Encoding",
                    "Last-Modified": formatdate(statobj.st_mtime, usegmt=True),
                    "Cache-Control": _get_cache_control(path, _is_hashed_asset(fullpath.name)),
                })
        headers = {
            "Last-Modified": formatdate(statobj.st_mtime, usegmt=True),
            "Cache-Control": _get_cache_control(path, _is_hashed_asset(fullpath.name)),
            "Vary": "Accept-Encoding",
        }
        if encoding:
            headers["Content-Encoding"] = encoding
        return FileResponse(fullpath, media_type=content_type, headers=headers)


def serve_static_file(request: Request, path: str, document_root) -> Response:
    """静态文件服务（对齐 django.views.static.serve：安全路径 + 304，无 Range/gzip）"""
    path = os.path.normpath(path).lstrip("/").replace("\\", "/")
    try:
        fullpath = _safe_join(document_root, path)
    except (PermissionError, OSError, ValueError):
        return _not_found(path)
    if fullpath.is_dir() or not fullpath.exists():
        return _not_found(path)
    statobj = fullpath.stat()
    if not _was_modified_since(request.headers.get("if-modified-since"),
                               statobj.st_mtime, statobj.st_size):
        return Response(status_code=304)
    headers = {"Last-Modified": formatdate(statobj.st_mtime, usegmt=True)}
    return FileResponse(fullpath, headers=headers)
