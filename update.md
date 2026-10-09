# 更新日志

## v2.0.1（2026-10-05）

### 新增
- 新增 FastAPI 版后端 `backend-fastapi`：接口、功能与 Django 版完全一致（含认证、CRUD、导入导出、日志中间件、WebSocket、节流、上传等全量能力），可与 Django 同时运行（8000 / 8001），前端零改动切换
- FastAPI 版资源完全独立：自带 `db.sqlite3` 数据库、`static/` 静态目录、`media/` 上传目录
- 附 `backend-fastapi/README.md`（启动、双跑切换、配置与部署说明）、`.env.prod` 生产配置模板、`.gitignore`

### 优化

- 重构优化前端管理页面，更符合现代审美UI

### 修复

- 无