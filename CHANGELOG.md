# dvlyadmin-fastapi 更新日志

## v1.0.0（2026-10-08）

### 新增
- 从 dvlyadmin-mini 剥离为独立项目：FastAPI 后端（`backend/`）+ Vue3 前端（`frontend/`）
- 根目录部署体系：Dockerfile（多阶段构建，前端产物集成部署）、docker-entrypoint.sh（Python 探测 MySQL → db_init 建表 → 首次 init）、.env.docker、build-and-push.bat、DOCKER.md
- .trae 工作区（规则 + 技能库）适配 FastAPI 形态

### 说明
- 接口路径/响应格式/JWT 与 dvlyadmin-mini Django 版互通，前端零改动
- 端口约定 8000，与 Django 版不可同时运行
