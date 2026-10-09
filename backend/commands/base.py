# -*- coding: utf-8 -*-
"""
@Remark: 管理命令基础设施（对应 Django BaseCommand 的骨架约定）
命令模块约定导出两个函数：
    add_arguments(parser)    注册命令参数（对应 Django Command.add_arguments）
    handle(args) -> int      执行命令并返回退出码（0 成功；对应 Django Command.handle）
"""
import argparse
import sys


def build_parser(name, description=None, prog=None):
    """创建命令级参数解析器（默认帮助信息显示为 python run.py <name>；manage.py 入口传入自己的 prog）"""
    return argparse.ArgumentParser(prog=prog or f"python run.py {name}", description=description)


def ok(message):
    """正常输出（对齐 Django self.stdout.write）"""
    print(message)


def err(message):
    """错误输出（对齐 Django self.stderr.write）"""
    print(message, file=sys.stderr)