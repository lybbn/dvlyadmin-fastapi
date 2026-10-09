# -*- coding: utf-8 -*-
"""
@Remark: 管理命令注册表（对应 Django manage.py 的命令体系）
用法：python run.py <命令名> [参数...]；python run.py --help 查看全部命令
新增命令：在 commands/ 下新建模块（约定 add_arguments(parser) + handle(args)），并在此注册
"""
COMMANDS = {
    "db_init": ("commands.db_init", "建库建表：按模型创建全部表（对既有库零副作用）"),
    "init": ("commands.init", "初始化数据：灌入与 Django 版一致的种子数据（-y/-Y 先删后建）"),
    "get_init_data": ("commands.get_init_data", "导出模型数据为 Python 字面量（粘贴回 initialize.py 用）"),
    "generate_token": ("commands.generate_token", "快速生成指定用户的 JWT token"),
    "startapp": ("commands.startapp", "在 apps/ 下生成新业务模块骨架"),
    "lystartapp": ("commands.startapp", "startapp 的兼容别名（对齐 Django 命令名）"),
}


def get_command(name):
    """按名称返回命令模块（未注册返回 None）"""
    import importlib

    item = COMMANDS.get(name)
    if item is None:
        return None
    return importlib.import_module(item[0])


def command_names():
    """命令名列表（别名不重复展示，保序）"""
    names, seen = [], set()
    for name, (module_path, _summary) in COMMANDS.items():
        if module_path in seen:
            continue
        seen.add(module_path)
        names.append(name)
    return names


def command_summary(name):
    """命令的一句话说明（python run.py --help 展示用）"""
    item = COMMANDS.get(name)
    return item[1] if item else ""