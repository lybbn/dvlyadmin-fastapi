# -*- coding: utf-8 -*-
"""
@Remark: 启动脚本（对应 Django manage.py：无参启动服务，子命令执行管理命令）
端口 8000，与 Django 版一致——前端无需改接口地址即可切换。
注意：同端口下两端不能同时运行，切换时先停掉另一端。
Django 风格入口见 manage.py（命令同源，额外支持 runserver/help，无需 Django 依赖）。
用法：
    python run.py                 # DEBUG=True 时自动带 --reload 启动服务
    python run.py --help          # 查看全部管理命令
    python run.py db_init         # 建库建表（唯一允许建表的入口）
    python run.py init [-y]       # 初始化数据（-y/-Y 先删后建；默认 upsert）
    python run.py get_init_data mysystem.Dept
    python run.py generate_token 用户ID
    python run.py startapp 模块名
"""
import sys


def _run_server():
    """启动 uvicorn 服务（原行为不变）"""
    import uvicorn

    from application.settings import DEBUG

    uvicorn.run(
        "application.main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
    )


def _print_help():
    """打印管理命令总览"""
    import commands

    print("用法: python run.py [命令] [参数...]")
    print("      无参数        启动服务（端口 8000，对应 Django manage.py runserver）")
    print()
    print("可用命令:")
    for name in commands.command_names():
        print(f"  {name:<16} {commands.command_summary(name)}")
    print()
    print("查看具体命令参数: python run.py <命令> -h")


def _run_command(name, argv):
    """执行管理命令并返回退出码"""
    import commands
    from commands.base import build_parser

    module = commands.get_command(name)
    if module is None:
        print(f"未知命令: {name}", file=sys.stderr)
        print(f"可用命令: {', '.join(commands.command_names())}", file=sys.stderr)
        return 2
    parser = build_parser(name, description=(module.__doc__ or "").strip())
    module.add_arguments(parser)
    args = parser.parse_args(argv)
    return module.handle(args) or 0


if __name__ == "__main__":
    _argv = sys.argv[1:]
    if not _argv:
        _run_server()
    elif _argv[0] in ("-h", "--help"):
        _print_help()
    elif _argv[0].startswith("-"):
        # 原 run.py 不解析任何参数，为保持兼容：非 -h/--help 的选项参数仍按原逻辑启动服务
        _run_server()
    else:
        sys.exit(_run_command(_argv[0], _argv[1:]))