# -*- coding: utf-8 -*-
"""
@Remark: Django 风格管理入口（对齐 manage.py 使用习惯；命令与 run.py 同源，共用 commands/ 注册表）
用法：
    python manage.py                     # 等价 help：列出全部子命令（对齐 Django 无参行为）
    python manage.py help [子命令]        # 查看命令总览 / 具体命令帮助
    python manage.py runserver [ip:port] # 启动服务（默认 0.0.0.0:8000；DEBUG=True 时自动热重载）
    python manage.py db_init             # 建库建表（唯一允许建表的入口）
    python manage.py init [-y]           # 初始化数据（-y/-Y 先删后建；默认 upsert）
    python manage.py get_init_data mysystem.Dept
    python manage.py generate_token 用户ID
    python manage.py lystartapp 模块名    # 在 apps/ 下生成新业务模块骨架（对齐 Django 命令名）
    python manage.py startapp 模块名      # 同上（本端命名）
"""
import sys

USAGE = "python manage.py <子命令> [参数...]"

# 命令分组展示（对齐 Django manage.py help 的 [app] 分段）
DJANGO_CUSTOM_COMMANDS = ("init", "get_init_data", "generate_token", "lystartapp")
BUILTIN_HELP = (
    ("help", "列出全部子命令 / 查看子命令帮助"),
    ("runserver", "启动服务：python manage.py runserver [ip:port]"),
)


def _subcommand_groups():
    """读取 commands/ 注册表并按分组返回 [(组名, [(命令名, 说明), ...]), ...]（组内按名称排序）"""
    import commands

    mysystem, fastapi = [], []
    for name in commands.COMMANDS:
        item = (name, commands.command_summary(name))
        (mysystem if name in DJANGO_CUSTOM_COMMANDS else fastapi).append(item)
    groups = (("[mysystem]", sorted(mysystem)), ("[fastapi]", sorted(fastapi)))
    return [(title, items) for title, items in groups if items]


def _print_help():
    """命令总览（对齐 manage.py 无参 / manage.py help 的输出）"""
    print(f"用法: {USAGE}")
    print()
    print("Type 'python manage.py help <subcommand>' for help on a specific subcommand.")
    print()
    print("Available subcommands:")
    print()
    for title, items in _subcommand_groups():
        print(title)
        for name, summary in items:
            print(f"  {name:<16}{summary}")
        print()
    print("[built-in]")
    for name, summary in BUILTIN_HELP:
        print(f"  {name:<16}{summary}")
    return 0


def _print_command_help(name):
    """查看子命令帮助（对齐 manage.py help <subcommand>）"""
    import commands
    from commands.base import build_parser

    if name == "help":
        print("用法: python manage.py help [子命令]")
        print("      不带参数     列出全部子命令")
        return 0
    if name == "runserver":
        print("用法: python manage.py runserver [ip:port]")
        print("      不带参数         0.0.0.0:8000（DEBUG=True 时自动热重载）")
        print("      8080             仅指定端口（监听 0.0.0.0）")
        print("      127.0.0.1:8080   指定地址与端口")
        return 0
    module = commands.get_command(name)
    if module is None:
        return _unknown_command(name)
    parser = build_parser(name, description=(module.__doc__ or "").strip(),
                          prog=f"python manage.py {name}")
    module.add_arguments(parser)
    parser.print_help()
    return 0


def _unknown_command(name):
    """未知命令提示（对齐 Django：Unknown command: 'xxx'. 输出到 stderr，退出码 1）"""
    print(f"Unknown command: '{name}'.", file=sys.stderr)
    print("Type 'python manage.py help' for usage.", file=sys.stderr)
    return 1


def _run_registry_command(name, argv):
    """执行 commands/ 注册表命令（与 python run.py <命令> 完全同源）"""
    import commands
    from commands.base import build_parser

    module = commands.get_command(name)
    if module is None:
        return _unknown_command(name)
    parser = build_parser(name, description=(module.__doc__ or "").strip(),
                          prog=f"python manage.py {name}")
    module.add_arguments(parser)
    args = parser.parse_args(argv)
    return module.handle(args) or 0


def _parse_addrport(value):
    """解析 runserver 的 [ip:port] / [port] 参数（对齐 Django），非法值抛 ValueError"""
    if ":" in value:
        host, _, port = value.rpartition(":")
        if not host or not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(value)
        return host, int(port)
    if not value.isdigit() or not 0 < int(value) < 65536:
        raise ValueError(value)
    return "0.0.0.0", int(value)


def _run_server(argv):
    """启动 uvicorn 服务（对齐 Django runserver；默认与 run.py 一致：0.0.0.0:8000）"""
    host, port = "0.0.0.0", 8000
    if argv:
        try:
            host, port = _parse_addrport(argv[0])
        except ValueError:
            print(f"Error: '{argv[0]}' is not a valid port number or address:port pair.")
            return 1
    import uvicorn

    from application.settings import DEBUG

    print(f"Starting development server at http://{host}:{port}/", flush=True)
    uvicorn.run("application.main:app", host=host, port=port, reload=DEBUG)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        return _print_help()
    name, rest = argv[0], argv[1:]
    if name == "help":
        return _print_command_help(rest[0]) if rest else _print_help()
    if name == "runserver":
        return _run_server(rest)
    return _run_registry_command(name, rest)


if __name__ == "__main__":
    sys.exit(main())