# dvlyadmin-fastapi 介绍

[![img](https://img.shields.io/badge/python-%3E=3.11.x-green.svg)](https://python.org/)  [![FastAPI](https://img.shields.io/badge/FastAPI-%3E=0.115.0-009688.svg)](https://fastapi.tiangolo.com/)  [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.x-red.svg)](https://docs.sqlalchemy.org/)  [![img](https://img.shields.io/badge/node-%3E%3D%2014.0.0-brightgreen)](https://nodejs.org/zh-cn/)

> 本项目是 **dvlyadmin-mini**（django-vue-lyadmin 精简版）的 **FastAPI 复刻独立版**：后端由 Django/DRF 整体替换为 FastAPI + SQLAlchemy 2.0，接口路径、请求/响应格式、JWT 认证与 Django 版完全互通，前端零改动切换。

## 🌟 简介

**dvlyadmin-fastapi** 保持 dvlyadmin-mini 的页面极致效果与小而精架构：前端采用 **Vite + Vue 3 + Element Plus**（支持适配手机端），后端采用 **FastAPI + SQLAlchemy 2.0（同步）+ PyMySQL**，接口与 dvlyadmin-mini Django 版完全对齐。

## 📦 同系列项目

lyadmin 系列提供了多语言/多框架的快速开发框架基座，前端均采用统一的 **Vite + Vue 3 + Element Plus** 设计风格，可按技术栈自由选择：

| 项目 | 技术栈 | 地址 |
| --- | --- | --- |
| **dvlyadmin-fastapi**（本项目） | Python + FastAPI | [https://gitee.com/lybbn/dvlyadmin-fastapi](https://gitee.com/lybbn/dvlyadmin-fastapi) |
| **dvlyadmin-mini** | Python + Django | [https://gitee.com/lybbn/dvlyadmin-mini](https://gitee.com/lybbn/dvlyadmin-mini) |
| **golyadmin** | Go (Golang) | [https://gitee.com/lybbn/golyadmin](https://gitee.com/lybbn/golyadmin) |

分别用于 **Django**、**FastAPI** 和 **Go 语言** 的快速开发框架基座，开箱即用，助力不同技术栈的团队快速搭建后台管理系统。

## 💡 与 Django 版（dvlyadmin-mini）的关系

| 维度 | dvlyadmin-mini（Django） | dvlyadmin-fastapi（本项目） |
|---|---|---|
| Web 框架 | Django 4.x + DRF | FastAPI |
| ORM | Django ORM | SQLAlchemy 2.0（同步 + 线程池并发） |
| 数据库驱动 | mysqlclient | PyMySQL（纯 Python，免编译） |
| 认证 | SimpleJWT | PyJWT（HS256，payload 结构与 Django 互通） |
| 建表方式 | `manage.py migrate` | `manage.py db_init`（checkfirst 幂等） |
| 端口 | 8000 | 8000（**两端不可同时运行**） |
| 前端 | 同一份 Vue3 前端 | 同一份 Vue3 前端（零改动） |


## 🛠️ 生态工具

### RuYi Panel — 服务器面板，快速部署发布项目

**RuYi Panel** 是一款用于**服务器面板快速部署发布项目**的运维管理面板，让项目部署像搭积木一样简单：官网地址：[https://ruyi.lybbn.cn](https://ruyi.lybbn.cn)

- 🖥️ 可视化服务器管理：站点、进程、环境一键配置
- 🚀 快速部署发布：无需手动敲命令，快速将项目发布上线
- 🔧 运维省心：日志查看、状态监控、常见运维操作面板化

### RuYi Workstation — 集中管理 RuYi Panel 的工作台（桌面版）

**RuYi Workstation** 用于**集中管理多台 RuYi Panel**，实现本地项目的快速一键发布和更新：

- 🗂️ 集中管理：在本地工作台中统一管理多台安装了 RuYi Panel 的服务器
- ⚡ 一键发布/更新：本地项目快速一键发布和更新到 RuYi Panel，告别繁琐的手工上传与重启
- 🔁 高效迭代：开发 → 发布 → 更新 流程一体化，大幅提升交付效率

## 🚀 快速开始（本地开发）

### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt   # Linux: venv/bin/python
venv\Scripts\python run.py db_init                        # 建表（幂等，可重复执行）
venv\Scripts\python run.py init                           # 初始化数据
venv\Scripts\python run.py                                # 启动服务（DEBUG=True 自动热重载）
```

本地默认使用 SQLite（`backend/db.sqlite3`），无需任何配置；连 MySQL 见 `backend/.env.dev` 内注释。

管理命令与 Django 对齐：`python manage.py runserver | db_init | init | get_init_data | generate_token | lystartapp`。

### 前端

```bash
cd frontend
npm install
npm run dev      # http://localhost:8081，代理指向后端 8000
npm run build    # 生产构建，产物 dist/
```

## 🎨 主要特性

- 💻 **前端技术栈**：Vue 3 + Setup JS + Pinia + Element Plus
- 🖥️ **后端技术栈**：FastAPI + SQLAlchemy 2.0 + PyMySQL
- 🔒 **认证系统**：JWT（HS256），与 Django SimpleJWT 完全互通，支持多终端认证
- ⚙️ **权限管理**：动态权限菜单，菜单按钮正则匹配鉴权（判定顺序与 Django 版一致）
- 📊 **列权限管控**：列权限管理机制，粒度细化到每一列
- ⚡️ **CRUD增强**：通用过滤/搜索/排序/导入导出，自定义 ViewSet 一行注册
- 🔌 **WebSocket**：消息推送 `/ws/msg/`（uvicorn 原生 ASGI）

## 💻 技术栈

### 前端

- **构建工具**：[Vite（极速构建）](https://vitejs.dev/)
- **框架**：[Vue 3（组合式 API）](https://vuejs.org/)
- **UI 组件库**：[Element Plus（企业级 UI）](https://element-plus.org/)
- **编程模式**：JavaScript Setup 语法糖

### 后端

- **Python**：>=Python3.11.x
- **FastAPI**：>=0.115.0（Uvicorn ASGI）
- **ORM**：SQLAlchemy 2.0.x（同步模式）
- **数据库**：MySQL（PyMySQL）/ SQLite（本地开发）

---

## 🐳 Docker 部署

详见 [DOCKER.md](DOCKER.md)。一键构建：`./build-and-push.bat`，运行：

```bash
docker run --restart unless-stopped -d --name dvlyadmin-fastapi -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v /opt/dvlyadmin-fastapi:/app/backend/data \
  dvlyadmin-fastapi:latest
```

容器内置前端构建产物（集成部署，`/` 直接访问后台页面），启动时自动建表与初始化数据。

---

## ❓ 常见问题解答

### 前端能否直接复用 dvlyadmin-mini 的？

**答**：可以。本项目 frontend 与 dvlyadmin-mini 完全同源，接口路径/响应格式/JWT 均互通，前端零改动。

### 添加菜单注意事项？

**答**：添加菜单时路由和组件名称最好与新建的菜单文件名一致，会自动发现并注册路由，无需填写【组件路径】，否则需填写此项！！！

### 如何快速实现导出功能？

**答**：继承了 CustomViewSet 方法的都会自动生成 export_data 接口，默认使用前端导出字段和 serializer_class 作为导出参数，也可单独配置实现导出自定义！！！

### Django 版与 FastAPI 版能同时运行吗？

**答**：不能同时占用 8000 端口。两端设计为同端口替换运行（前端无需改接口地址），切换时先停掉另一端。

---

### 目录介绍

```
backend/                # 后端代码目录（FastAPI）
frontend/               # 前端代码目录（Vue3）
```

## ✅ 演示图

![登录](https://foruda.gitee.com/images/1791506066046958975/0afded43_4823422.png "登录")

![首页](https://foruda.gitee.com/images/1791506090585942679/c911f3c0_4823422.png "首页")

![个人中心](https://foruda.gitee.com/images/1791506113770100872/d018f51c_4823422.png "个人中心")

![用户管理](https://foruda.gitee.com/images/1791506152816908706/10da2d6c_4823422.png "用户管理")

![菜单管理](https://foruda.gitee.com/images/1791506182507712082/1c7200ca_4823422.png "菜单管理")

![权限管理](https://foruda.gitee.com/images/1791506207427706092/d1379195_4823422.png "权限管理")

![系统配置](https://foruda.gitee.com/images/1791506241678582214/697cd48c_4823422.png "系统配置")

![字典管理](https://foruda.gitee.com/images/1791506271356529319/5f28d5e4_4823422.png "字典管理")
