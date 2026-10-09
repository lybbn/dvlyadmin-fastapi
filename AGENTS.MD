# AGENTS.md — AI Agent 引导

dvlyadmin-fastapi：FastAPI + SQLAlchemy 2.0 后端（`backend/`），Vue3 + Element Plus 前端（`frontend/`）。本项目是 dvlyadmin-mini（Django 版）的 FastAPI 复刻独立版，接口与 Django 版互通，前端零改动。

## 目录结构（规则与技能入口）

```
.trae/
├── rules/                     # 项目强制规则，动手前必读
│   └── AGENTS.md              # 建表保护（db_init 唯一入口）+ FK 字段映射 + 底层框架保护
├── documents/                 # 设计文档（fastapi 独立化方案等）
└── skills/                    # 技能库，每个子目录一个 SKILL.md
    ├── dvlyadmin-json-response/        # 响应类用法（FastAPI 版同样适用：utils/jsonResponse 同名类）
    ├── dvlyadmin-initialize-data/      # 初始化数据（对应 commands/init + mysystem/initialize.py）
    ├── dvlyadmin-pagination-habits/
    ├── dvlyadmin-lydialog-habits/
    ├── dvlyadmin-element-plus-icons-habits/
    ├── dvlyadmin-svgicon-habits/
    ├── add-devtool/
    ├── case-illustration/
    ├── frontend-design/
    ├── ui-ux-pro-max/
    ├── ui-styling/
    ├── design-system/
    ├── design/
    ├── brand/
    ├── banner-design/
    └── slides/
```

## 必守规则

**严禁绕过 `db_init` 建表/改表**：本项目无 Django migrations，`python run.py db_init`（checkfirst 幂等）是唯一建表入口；禁止手写建表 SQL、禁止业务代码调用 `create_all`。详见 `.trae/rules/AGENTS.md`。

**手写过滤器 FK 字段映射**：Django FK 字段名（如 `parent`、`menu`）在 SQLAlchemy 模型中是 `*_id` 字符串列（无 relationship），手写过滤器必须映射到 `*_id` 列（参照 `mysystem/views/system_config.py`：`col = f"{field}_id" if field == "parent" else field`）。直接 `getattr(Model, "parent")` 会 AttributeError → 500 → 前端报"网络连接错误"。通用链路 `utils/filters.py` 的 `_resolve_column` 已内置此映射兜底，优先走 `filterset_fields`/`search_fields` 声明而非手写循环。

**响应格式互通**：HTTP 200 + body.code 业务码，必须用 `utils/jsonResponse` 的 SuccessResponse/DetailResponse/ErrorResponse，与 Django 版格式一致。

## Skills（任务命中场景时，先读对应 `.trae/skills/<name>/SKILL.md` 再写代码）

## 原则

优先用框架内置能力，不改底层源码；组件用法不确定时查 SKILL.md，不猜测。后端改动保持与 Django 版（dvlyadmin-mini）行为对齐——接口路径（含结尾斜杠）、响应结构、权限判定顺序均不得漂移。
