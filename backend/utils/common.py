# -*- coding: utf-8 -*-
"""
@Remark: 公用方法（对应 Django utils/common.py，按需移植常用函数）
"""
import ast
import datetime
import json
import os
import random
import re
import time

# 手机号验证正则
REGEX_MOBILE = r"^1[356789]\d{9}$|^147\d{8}$|^176\d{8}$"


def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.fullmatch(pattern, email))


def formatdatetime(datatimes):
    """
    格式化日期时间为指定格式
    :param datatimes: 数据库中存储的datetime日期时间,也可以是字符串形式(2021-09-23 11:22:03.1232000)
    :return: 格式化后的日期时间如：2021-09-23 11:22:03
    """
    if datatimes:
        try:
            if isinstance(datatimes, str):
                if "." in datatimes:
                    arrays = datatimes.split(".", maxsplit=1)
                    if arrays:
                        return arrays[0]
            return datatimes.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return datatimes
    return datatimes


def ast_convert(value):
    """把字符串转换成数组对象等（对齐 Django utils/common.ast_convert）"""
    if value:
        try:
            return ast.literal_eval(value)
        except Exception:
            return value
    return None


def ast_convert_str(arr):
    """把数组对象转换成字符串（对齐 Django utils/common.ast_convert_str）"""
    if arr:
        try:
            if isinstance(arr, str):
                return arr
            if isinstance(arr, (dict, list)):
                return json.dumps(arr, ensure_ascii=False)
        except Exception:
            return arr
    return None


def boolValue(val):
    """字符串/None → bool（对齐 mysystem/views/system_config.boolValue）"""
    if isinstance(val, bool):
        return val
    if not val:
        return False
    elif val.lower() in ["true", "1", 't', 'y', 'yes', 'on']:
        return True
    elif val.lower() in ["false", "0", 'f', 'n', 'no', 'off']:
        return False
    else:
        raise ValueError(f"Cannot convert '{val}' to boolean")


def safe_parse_json(value):
    """安全 JSON 解析（处理可能的外层引号，对齐 system_config.safe_parse_json）"""
    try:
        if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def get_parameter_dic(request, body=None):
    """
    获取 get 或 post 的参数（对齐 Django utils/common.get_parameter_dic）
    (1) query 参数非空时优先返回 query，否则返回 body
    (2) FastAPI 版：request 为 starlette Request，body 为已解析的 dict/None
    """
    query_params = {k: v for k, v in request.query_params.items()}
    if query_params != {}:
        return query_params
    if isinstance(body, dict):
        return body
    return {}


def renameuploadimg(srcimg):
    """上传图片重命名（对齐 Django utils/common.renameuploadimg）：年月日时分秒_随机数 + 扩展名"""
    ext = os.path.splitext(srcimg)[1]
    # File names longer than 255 characters can cause problems on older OSes.
    if len(srcimg) > 255:
        ext = ext[:255]
    # 定义文件名，年月日时分秒随机数
    fn = time.strftime('%Y%m%d%H%M%S')
    fn = fn + '_%d' % random.randint(100, 999)
    # 重写合成文件名
    return fn + ext
