# 项目全局规则（FastAPI 版）

## 行为约束

### 数据库建表保护（对齐 Django Migration 保护规则）

**核心原则：`db_init` 是本项目唯一允许建表的入口，严禁绕过它建表/改表。**

本项目无 Django migrations，表结构由 SQLAlchemy 模型定义，由 `db_init` 命令（`Base.metadata.create_all(checkfirst=True)`）承载建表职责。

#### 允许的操作

1. ✅ **运行 `python run.py db_init` / `python manage.py db_init`** - 幂等建表（已有表不受影响）
2. ✅ **读取和分析 models.py** - 了解表结构
3. ✅ **修改 models.py 增加列后** - 告知用户 SQLite 不支持自动加列，需重建库或手动 ALTER

#### 禁止的操作

1. ❌ **手写 SQL 建表/改表脚本** 入库执行
2. ❌ **在业务代码中调用** `Base.metadata.create_all` 或 `engine.execute("CREATE TABLE ...")`
3. ❌ **删除/重命名已有表** 的操作（`db_init` 的 checkfirst 不会改已有表，也不允许其他途径改）

#### 模型变更流程

1. 修改 `mysystem/models.py`（或 `apps/*/models.py`）中的模型
2. 新增表/新库 → 跑 `db_init` 即可；已有表加列 → 告知用户手动迁移或重建库
3. 同步初始化数据 → `run.py get_init_data` / `init` 流程

### FK 字段映射规则（SQLAlchemy 无 relationship）

Django FK 字段名（如 `parent`、`menu`、`creator`）在本项目 SQLAlchemy 模型中是 `*_id` 字符串列（`db_constraint=False` 的复刻约定，无 relationship）：

1. ✅ **手写过滤器必须映射**：`col = f"{field}_id" if field == "parent" else field`（参照 `mysystem/views/system_config.py`）
2. ✅ **优先走通用链路**：`filterset_fields` / `search_fields` 声明（`utils/filters.py` 的 `_resolve_column` 已内置 `*_id` 映射兜底）
3. ❌ **禁止** `getattr(Model, "parent")` 直接取 Django FK 名 → AttributeError → 500 → 前端"网络连接错误"（`mysystem/views/dictionary.py` 曾踩坑）

### 底层框架保护

- `application/`、`utils/`（除业务必需外）、`commands/` 为框架层，改动需谨慎并说明理由
- 响应格式必须使用 `utils/jsonResponse` 的 SuccessResponse / DetailResponse / ErrorResponse（与 Django 版格式互通：HTTP 200 + body.code 业务码）

---
