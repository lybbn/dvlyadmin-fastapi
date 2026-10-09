#  Docker 部署（dvlyadmin-fastapi）

镜像内置：前端 Vue3 构建产物（集成部署） + FastAPI 后端（uvicorn，端口 8000）。
启动时自动：等待 MySQL 就绪 → `db_init` 建表（幂等）→ 首次 `init` 初始化数据 → 启动服务。

## 1. Docker 推送

```bash
docker build -f Dockerfile -t dvlyadmin-fastapi:latest .
docker images
docker tag bf8xxxxx registry.cn-beijing.aliyuncs.com/django-vue-lyadmin/dvlyadmin-fastapi:latest
docker push registry.cn-beijing.aliyuncs.com/django-vue-lyadmin/dvlyadmin-fastapi:latest
```

## 2. 部署到生产环境（运行容器）

```bash
docker pull registry.cn-beijing.aliyuncs.com/django-vue-lyadmin/dvlyadmin-fastapi:latest
docker run --restart unless-stopped -d --name dvlyadmin-fastapi -p 8000:8000 --add-host=host.docker.internal:host-gateway -v /opt/dvlyadmin-fastapi:/app/backend/data registry.cn-beijing.aliyuncs.com/django-vue-lyadmin/dvlyadmin-fastapi:latest
```

- 宿主只需挂载 `/app/backend/data` 一个目录（media/logs 上传与日志自动软链至其子目录）
- 与 Django 版（dvlyadmin-mini）共用 8000 端口约定不变，但**两者不可同时运行在同一台宿主机的 8000 端口**
- 数据库默认独立（`dvlyadmin_fastapi`），可在 `.env.docker` 中改回与 Django 版同库

## 3. 直接一键打包部署

```bash
./build-and-push.bat
```

## 4. 环境变量

见 [.env.docker](.env.docker)。修改后重建容器生效（变量在启动时由 entrypoint 加载）。

## 5. 与 Django 版 Docker 的差异

| 项目 | Django 版 | FastAPI 版 |
|---|---|---|
| 应用服务器 | daphne（ASGI） | uvicorn（ASGI，原生 WebSocket） |
| 建表方式 | `manage.py migrate` | `manage.py db_init`（checkfirst 幂等建表） |
| 静态文件 | `collectstatic` 收集 | 构建期直接 COPY 归位（无收集步骤） |
| MySQL 等待 | mysqladmin ping | 内置 Python 探测（镜像更精简，无 mysql-client） |
