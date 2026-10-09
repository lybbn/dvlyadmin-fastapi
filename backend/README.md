# dvlyadmin-mini 后端 FastAPI 复刻版

用 FastAPI 完整复刻 Django 后端（`../backend`）的接口与功能：**接口路径、请求/响应格式、文件夹布局与 Django 版一一对应**。端口与 Django 版一致（8000），前端零改动即可切换；数据库、静态、媒体资源完全独立（自有 `db.sqlite3` / `static/` / `media/`，初始内容从 Django 端复制而来，之后各自演化互不影响）。

## 目录结构（与 Django 版对应）

```
backend-fastapi/
├── config.py              # 环境配置加载（对应 backend/config.py，环境变量名一致）
├── .env.dev               # 开发环境配置档案（自动加载，可提交）
├── run.py                 # 启动脚本 + 管理命令入口（对应 Django manage.py）
├── manage.py              # Django 风格入口（命令与 run.py 同源；支持 help / runserver）
├── commands/              # 管理命令（对应 mysystem/management/commands/）
├── requirements.txt       # 依赖清单
├── application/
│   ├── main.py            # FastAPI app 入口（对应 wsgi/asgi.py）
│   ├── settings.py        # 全局配置聚合（对应 application/settings.py）
│   ├── database.py        # SQLAlchemy 引擎/会话（对应 Django ORM 连接层）
│   └── urls.py            # 总路由（对应 application/urls.py，路径完全一致）
├── mysystem/
│   ├── models.py          # SQLAlchemy 表映射（只映射 lyadmin_* 表，绝不建表/改表）
│   ├── schemas.py         # Pydantic 模型
│   ├── initialize.py      # 初始化数据（种子与 Django 版逐字一致）
│   ├── urls.py            # 业务路由注册（对应 mysystem/urls.py）
│   └── views/             # 15 个业务视图（menu/role/dept/user/... 与 Django 同名同职责）
├── apps/                  # 新业务模块目录（python run.py startapp 生成）
├── utils/                 # 公共层（viewset/serializers/permission/middleware/... 同名同职责）
├── static/                # 本项目自有静态目录（已从 backend/static 同步）
├── media/                 # 本项目自有上传文件目录（已从 backend/media 同步）
└── logs/                  # 运行日志（server.log / error.log）
```

## 快速启动（本地开发）

```bash
cd backend-fastapi

# 1. 安装依赖（建议虚拟环境）
pip install -r requirements.txt

# 2. 启动（端口 8000）
python run.py
```

启动后访问：

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/api/captcha/ | 验证码接口（连通性自测） |
| http://127.0.0.1:8000/static/favicon.ico | 静态资源 |
| http://127.0.0.1:8000/docs | FastAPI 自动生成的接口文档（仅开发用） |

`python run.py` 等价于：

```bash
uvicorn application.main:app --host 0.0.0.0 --port 8000 --reload
```

`DEBUG=True`（开发默认）时 `run.py` 自动带 `--reload`，代码改动即时生效。

Django 风格入口：`python manage.py runserver`（与 `python run.py` 等价，详见"管理命令"章节）。

## 管理命令（独立运行，无 Django 依赖）

提供两个等价入口，命令同源（`python manage.py init` 与 `python run.py init` 完全一致），按习惯任选：

- `python run.py ...`：本端原生入口——无参启动服务，`--help` 查看命令
- `python manage.py ...`：Django 风格入口——无参/`help` 列出子命令，`help <命令>` 查看帮助，`runserver [ip:port]` 启动服务（默认 0.0.0.0:8000）

内置与 Django 版对应的管理命令，**不依赖任何 Django 组件**即可独立建库、灌初始数据、扩展新模块：

| FastAPI 用法 | Django 对应 | 说明 |
|---|---|---|
| `python run.py` | `python manage.py runserver` | 启动服务（8000），行为完全不变 |
| `python run.py db_init` | （承载 migrate 的建表职责） | 按模型创建全部表；对既有库只补齐缺表，不重建、不改表、不丢数据 |
| `python run.py init [-y]` | `python manage.py init` | 灌初始数据；`-y/-Y` 先删后建，默认 upsert（幂等）；可指定模块名（如 `init mysystem`） |
| `python run.py get_init_data mysystem.Dept` | `python manage.py get_init_data ...` | 导出模型数据为 Python 字面量（含行尾逗号，可直接粘贴回 initialize.py） |
| `python run.py generate_token 用户ID` | `python manage.py generate_token 用户ID` | 签发 JWT（`{identity, userId, refresh, access}`，与 simplejwt 完全互通） |
| `python run.py startapp 模块名` | `python manage.py lystartapp 模块名` | 在 `apps/` 生成新业务模块骨架（`lystartapp` 为兼容别名） |

**从零独立建库**（无 Django 环境）：

```bash
cd backend-fastapi
pip install -r requirements.txt
python run.py db_init    # 建表（本项目唯一允许建表的入口）
python run.py init       # 灌初始数据（账号与 Django 版一致：superadmin / admin / test）
python run.py            # 启动服务
```

（以上命令亦可用 Django 风格入口：`python manage.py db_init` / `python manage.py init` / `python manage.py runserver`）

**两套工作流互不冲突**：

- **复制库工作流**：新表/新字段仍由 Django 端 migrations 管理，变更后复制 `db.sqlite3` 到本端（`db_init` 对已有表零副作用）；
- **独立工作流**：无 Django 环境时用 `db_init` 建表，`startapp` 扩展新模块——`apps/*/models.py` 会被 `db_init` 自动建表，`apps/*/initialize.py` 会被 `init` 自动执行（对齐 Django 遍历 `INSTALLED_APPS` 的语义）。

**与 Django 命令的有意差异**（其余语义完全一致）：

1. `init` 的模块名位置参数在本端生效（可只执行指定模块；Django 解析但忽略）
2. `get_init_data --exclude` 在本端生效（覆盖默认排除字段；Django 为 no-op）

## 与 Django 版切换（同端口替换）

两端同为 **8000 端口**，**不能同时运行**——切换时先停掉运行中的一端，再启动另一端：

```bash
# Django 版
cd backend
python manage.py runserver 0.0.0.0:8000

# 或 FastAPI 版（两种入口等价）
cd backend-fastapi
python run.py
# python manage.py runserver
```

前端**无需任何改动**：接口地址不变，停 Django 启 FastAPI 即完成切换。JWT 与密码两端互通（同一 SECRET_KEY、同一 pbkdf2_sha256 算法），同一账号可在两端登录，但**业务数据互不相通**（各自独立库）。

## 配置说明

配置加载优先级（`config.py` 启动时自动执行，命中即停）：

1. `backend-fastapi/.env` —— 部署实际生效配置（服务器上从 `.env.prod` 复制，**不入 git**）
2. `.env.{DVLYADMIN_ENV}` —— 环境变量显式指定（如 `DVLYADMIN_ENV=prod` 加载 `.env.prod`）
3. `.env.dev` —— 本地开发默认档案（已提供）

本地开发默认（`.env.dev`）：SQLite 使用本项目自己的 `db.sqlite3`、内存缓存代替 Redis、`DOMAIN_HOST=http://127.0.0.1:8000`。所有环境变量以 `DVLYADMIN_` 前缀，含义与 Django 版一致。

## 与 Django 版的关键差异

| 项 | Django 版 | FastAPI 版 |
|---|---|---|
| 端口 | 8000 | 8000（同端口替换，不可同跑） |
| ORM | Django ORM | SQLAlchemy 2.0（同步，线程池并发） |
| 表结构 | migrations 管理 | 复制库工作流：只映射不建表；独立工作流：`run.py db_init` 建表 |
| JWT | simplejwt | PyJWT HS256（payload 对齐 simplejwt，完全互通） |
| WebSocket | channels | FastAPI 原生 WebSocket + ConnectionManager |
| 数据库/静态/媒体 | `backend/db.sqlite3`、`backend/static`、`backend/media` | 本项目自有 `db.sqlite3`、`static/`、`media/`（初始库与静态/媒体均从 Django 同步一次，之后各自演化） |

## 注意事项

- **资源完全独立**：FastAPI 版的数据库（`db.sqlite3`）、静态（`static/`）、媒体（`media/`）均与 Django 端独立，初始内容从 Django 端复制；两端后续数据各自演化互不影响
- **重新同步**：如需用 Django 端最新数据重置 FastAPI 库，停掉两端服务后执行 `Copy-Item backend\db.sqlite3 backend-fastapi\db.sqlite3 -Force`（PowerShell）或 `copy /Y backend\db.sqlite3 backend-fastapi\db.sqlite3`（CMD）
- **表结构变更**：新表/新字段仍由 Django 端 migrations 管理；变更后重新复制库文件到本端即可（表结构由 Django 保证）。无 Django 环境时用 `python run.py db_init` 建表并独立开发（详见"管理命令"章节）
- **生产部署**：`cp .env.dev .env` 后修改为真实值；`DEBUG=False`；用 `uvicorn application.main:app --host 0.0.0.0 --port 8000`（多进程加 `--workers N`）启动
