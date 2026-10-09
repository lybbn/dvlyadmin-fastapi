---
name: "dvlyadmin-initialize-data"
description: "指导如何在 dvlyadmin-fastapi 项目中通过 initialize.py 添加初始化数据。Invoke when user wants to add seed/init data to database or create new init methods."
---

# dvlyadmin-fastapi 初始化数据添加指南

> 本项目为 FastAPI + SQLAlchemy 2.0 架构（非 Django）。无 Django ORM/migrations，FK 均为 `*_id` 字符串列（无 relationship），m2m 通过 through 表 + `M2M_FIELDS` 显式映射。

## 核心文件

- **初始化类**: `backend/mysystem/initialize.py` — `Initialize` 类（构造签名 `Initialize(db, delete=False)`，需传 SQLAlchemy 会话）+ `main(is_delete=False)` 入口函数
- **初始化命令**: `backend/commands/init.py` — `python run.py init [-y]` 或 `python manage.py init [-y]`（两入口同源）
- **反向生成命令**: `backend/commands/get_init_data.py` — 从数据库读取已有数据生成初始化代码
- **建表命令**: `backend/commands/db_init.py` — `python run.py db_init`，本项目**唯一允许建表的入口**（新模型必须先执行）

## 执行方式

所有命令均在 `backend/` 目录下运行（导入路径为 `mysystem.models` 形式，依赖 cwd）。

### 整体初始化（全部执行）
```bash
cd dvlyadmin-fastapi\backend
python run.py init          # 默认 upsert：已有数据直接更新，无则新建
python run.py init -y       # 先删除种子数据再重新创建（级联删除，对齐 Django Collector 规则）
```

`init` 命令会依次执行 `mysystem/initialize.py` 与 `apps/*/initialize.py`（存在则执行），调用各模块的 `main(is_delete=...)`。

### 只初始化指定模块
```bash
python run.py init mysystem        # 只执行 mysystem
python run.py init demoapp         # 只执行 apps/demoapp（自动识别 apps/ 下的模块）
```

### 单独初始化某个方法
本项目无 Django shell，用 `python -c` 手动调用（注意需自建会话）：
```bash
python -c "from mysystem.initialize import Initialize; from application.database import SessionLocal; db = SessionLocal(); Initialize(db).init_dept(); db.close()"
```

### 获取数据库已有数据（反向生成初始化代码）
```bash
python run.py get_init_data mysystem.Dept
python run.py get_init_data mysystem.Menu
python run.py get_init_data mysystem.Role
```
此命令会输出模型数据为 Python dict 格式（`str(dict) + ','` 每行一条），可直接复制到 `initialize.py` 中使用。

可选参数：
- `--fields name,key` 只获取指定字段
- `--exclude sort` 排除指定字段（默认已排除：create_datetime, update_datetime, is_delete, modifier, dept_belong）
- `--order_by sort` 按指定字段排序（默认：id）

注意：`get_init_data` 当前仅解析 `mysystem.models` 中的模型（格式 `mysystem.ModelName`，兼容裸类名）。

---

## 添加新初始化数据的步骤

### 0. 新模型先建表（强制）
如果初始化数据涉及**新模型/新表**，必须先执行（严禁手写 SQL 建表）：
```bash
python run.py db_init    # 幂等建表：已有表不受影响，只创建缺失的表
```
已有表加列：SQLite 不支持自动加列，需手动 ALTER 或重建库。

### 1. 在 Initialize 类中添加 init 方法

方法命名规则：`init_{名称}`，如 `init_brand`

```python
def init_brand(self):
    """
    初始化品牌数据
    python run.py get_init_data mysystem.Brand
    """
    data = [
        {
            'id': 'brand_001',             # 必须指定固定ID，用于 upsert
            'creator_id': '0',             # creator_id='0' 表示系统创建
            'name': '品牌名称',
            'sort': 1,
            'status': True,
        },
        # ... 更多数据
    ]
    self.save(Brand, data, "品牌数据")
```

### 2. 在 Initialize.run() 中注册

在 `run()` 方法中添加调用（注意顺序，有依赖关系的放后面）：

```python
def run(self):
    try:
        self.init_dept()
        self.init_button()
        self.init_menu()
        # ... 已有的 init 方法
        self.init_brand()   # 新增
        print("所有初始化完成!")
    except Exception as e:
        print(f"初始化过程中出错: {str(e)}")
```

### 3. 在文件顶部导入模型

```python
from mysystem.models import (Button, Dept, Dictionary, Menu, MenuButton, Notification,
                             NotificationUsers, Role, SystemConfig, Users, Brand)
```

### 4. m2m 关联必须先注册 M2M_FIELDS（本端特有）

SQLAlchemy 无 relationship，`save()` 中所有 **list 类型的值**按 m2m 处理，但必须先在 `initialize.py` 顶部的 `M2M_FIELDS` 注册 through 表映射，否则抛 `ValueError: 未映射的关联字段` 并回滚该条数据：

```python
# 格式: (模型类名, 字段名): (through 模型, 主体列, 目标列)
M2M_FIELDS = {
    ("Users", "role"): (UsersRole, "users_id", "role_id"),
}
```

新业务模型如有多对多关联（自建 through 表），同样在此登记。

---

## save() 方法规则

`self.save(model, data, name)` 是通用保存方法，核心逻辑（对齐 Django 版语义）：

- **upsert**：`db.get(model, pk)` 主键存在则逐字段 setattr 更新（跳过 id），不存在则按显式 id 新建 —— 对齐 Django `update_or_create(id=..., defaults=...)`
- **delete=True（`init -y`）**：先删除 data 中所有 id 对应的记录再重建；删除复用 `utils.viewset.apply_cascade`（级联与 PROTECT 规则对齐 Django Collector）
- 每条记录独立 try/except，单条失败回滚该条并打印错误，不影响其余

字段处理规则：

| 字段类型 | 正确做法 |
|---------|---------|
| 普通字段（str/int/bool） | 直接赋值，放在 data dict 中 |
| FK 外键 | 用 `{field}_id` 字符串列名（如 `parent_id`、`menu_id`），值为目标 id |
| m2m 多对多 | 用 Django 字段名（如 `role`）传 id 的 **list**，且必须在 `M2M_FIELDS` 已注册 |
| JSON/TEXT 字段（值为 dict） | 直接用 Python dict 赋值（模型端自行序列化时按模型定义） |
| JSON/TEXT 字段（值为 list） | **不能直接放在 data dict 中**（会被误当 m2m 处理），需特殊处理（见下方） |

**字段值为 list 的处理方式**：

先保存主体数据（不含该字段），再单独赋值：

```python
def init_my_data(self):
    data = [
        {'id': '1', 'name': '测试', 'role': ['role_id_1']},  # role 是已注册的 m2m
    ]
    self.save(MyModel, data, "测试数据")

    # JSON/TEXT 字段值为 list 的，需要单独处理
    obj = self.db.get(MyModel, '1')
    obj.json_list_field = ['value1', 'value2']
    self.db.commit()
```

---

## 数据 ID 规范

- 必须为每条数据指定固定 ID，确保重复执行不会产生重复数据
- `creator_id` 设为 `'0'` 表示系统级数据
- FK 字段一律使用 `{field}_id` 格式（如 `parent_id`、`role_id`）；m2m 字段用 Django 侧字段名（如 `role`）
- ID 命名建议：`{模块缩写}_{序号}`（系统模块沿用 Django 版的 32 位 hex id），如 `brand_001`、`menu_001`

## 现有初始化方法参考（mysystem/initialize.py）

```python
def init_dept(self):                # 部门信息
def init_button(self):              # 权限按钮标识
def init_menu(self):                # 菜单表
def init_menu_button(self):         # 菜单权限按钮
def init_role(self):                # 角色
def init_users(self):               # 用户（含 Users.role m2m 示例）
def init_notification(self):        # 通知
def init_notification_users(self):  # 通知用户
def init_systemconfig(self):        # 系统配置
def init_dictionary(self):          # 字典管理
```

## apps 业务模块的初始化数据

`init` 命令会自动发现 `apps/<模块>/initialize.py`（存在即执行），要求该文件提供 `main(is_delete=False)` 入口，可参照 `mysystem/initialize.py` 的结构实现（自建 `SessionLocal` 会话 + Initialize 类）。

## 反向操作：从数据库生成初始化数据

1. 先在管理后台或 API 中手动创建数据
2. 运行 `python run.py get_init_data mysystem.ModelName` 获取 dict 格式数据
3. 将输出复制到 `initialize.py` 的 `init_xxx` 方法中
