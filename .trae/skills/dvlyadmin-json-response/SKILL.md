---
name: "dvlyadmin-json-response"
description: "指导如何在 dvlyadmin-fastapi 项目中正确使用 SuccessResponse、DetailResponse、ErrorResponse 响应类。当编写 FastAPI 视图返回数据时，必须调用此 skill 获取正确的响应方式。"
---

# FastAPI 响应类使用指南（对齐 Django 版格式）

## 响应类位置
`backend/utils/jsonResponse.py`（基于 FastAPI `JSONResponse` + `jsonable_encoder`）

## 核心约定（与 Django 版互通）

1. **HTTP 状态码恒为 200**，业务码放 body.code，前端只认 body.code
2. 出站统一经 `rewrite_loopback` 改写回环地址（对齐 DJ LoopbackRewriteJSONRenderer）
3. 前端判断成功条件：`res.code === 2000`

## 三种响应类概述

| 响应类 | 用途 | 返回格式 |
|--------|------|----------|
| `SuccessResponse` | 分页列表数据 | data 内含 page、limit、total、data |
| `DetailResponse` | 单条数据或非分页数据 | 直接返回 data |
| `ErrorResponse` | 错误信息 | 包含 code、msg、data |

## 函数签名（实际源码）

```python
SuccessResponse(data=None, msg='success', page=1, limit=1, total=1, code=2000, headers=None)
DetailResponse(data=None, msg='success', code=2000, headers=None)
ErrorResponse(data=None, msg='error', code=400, status=None, headers=None)
```

- **SuccessResponse**：`data` 为空时 `total` 自动归零（对齐 DRF `if not data: total = 0`）
- **DetailResponse**：单条/非分页数据
- **ErrorResponse**：默认业务码 400；`status` 参数可改 HTTP 状态码（默认仍为 200）

## 返回格式

### SuccessResponse
```json
{
    "code": 2000,
    "data": {
        "page": 1,
        "limit": 10,
        "total": 100,
        "data": [...]
    },
    "msg": "success"
}
```

### DetailResponse
```json
{
    "code": 2000,
    "data": {...},
    "msg": "success"
}
```

### ErrorResponse
```json
{
    "code": 400,
    "data": null,
    "msg": "error"
}
```

## 业务码约定（本项目实际）

| 业务码 | 含义 | 来源 |
|--------|------|------|
| 2000 | 成功 | SuccessResponse / DetailResponse / paginate_response |
| 400 | 默认业务错误 | ErrorResponse 默认值 |
| 4000 | 业务/校验/权限错误（统一） | APIException / PermissionDeniedError / 路由异常 |
| 4001 | 认证失败（前端据此跳登录） | AuthenticationError |
| 404 | 路由地址不存在 | StarletteHTTPException(404) |

> 注意：与 Django 版不同，本项目异常处理器对**所有** `APIException` 统一返回业务码 4000（`AuthenticationError` 除外 → 4001），`exc.code` 不参与响应。见 `utils/exception.py`。

## 导入方式

```python
from utils.jsonResponse import SuccessResponse, DetailResponse, ErrorResponse
```

## 视图编写模式（FastAPI 版，与 DRF 不同）

本项目视图是**声明式类**（继承 `CustomViewSet`），方法**无 request 参数**，上下文从 `self.request / self.db / self.user` 取：

```python
from utils.common import get_parameter_dic
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.viewset import CustomViewSet

class DeptViewSet(CustomViewSet):
    model = Dept
    serializer_class = DeptSerializer
    filterset_class = DeptFilterSet()      # 可调用过滤器：__call__(db, request, query) -> query
    search_fields = ['name', 'owner']      # 或用 filterset_fields 声明式过滤

    def set_status(self):
        """自定义 action（由 urls.py 的 register_action 注册）"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id", "")
        query = self.filter_queryset(self.get_queryset()).where(Dept.id == id)
        instance = self.db.execute(query).scalars().first()
        if instance:
            instance.status = False if instance.status else True
            self.db.commit()
            return DetailResponse(data=None, msg="设置成功")
        else:
            return ErrorResponse(msg="未获取到数据")
```

常用上下文方法：
- `self.get_request_data()` → JSON body（对齐 DRF `request.data`，中间件预解析到 `request.state.body`）
- `get_parameter_dic(self.request, self.get_request_data())` → 合并 query 参数与 body
- `self.get_queryset()` / `self.filter_queryset(query)` → 基础查询 / 数据权限+过滤+搜索+排序
- `self.get_object()` → 不存在抛 404（由全局异常处理器转业务码 404）
- `self.get_serializer()` → 序列化器实例（`serializer.run_validation(data)` 校验、`serialize/serialize_many` 输出）

## 何时使用

### SuccessResponse - 分页列表场景
标准 CRUD 的 list 由基类 `CustomViewSet.list()` 自动处理（内部走 `paginate_queryset` + `paginate_response`），一般无需手写。需手写分页时（自定义列表接口）：

```python
from utils.pagination import paginate_queryset, paginate_response

def my_list(self):
    query = self.filter_queryset(self.get_queryset())
    items, total, page, limit = paginate_queryset(self.db, self.request, query)
    data = self.get_serializer().serialize_many(items)
    return paginate_response(self.request, data, total, page, limit)
```

`paginate_response` 与 DRF CustomPagination 对齐：无数据时自动返回 `msg="暂无数据"`、`total=0`。

### DetailResponse - 单条数据场景
- 获取详情（基类 retrieve 已处理）
- 创建/更新成功返回数据（基类 create/update 已处理，msg 为"新增成功"/"更新成功"）
- 不需要分页的数据列表：`return DetailResponse(data=serializer.serialize_many(items))`
- 操作成功提示（无返回数据）：`return DetailResponse(data=None, msg="启用成功")`

### ErrorResponse - 错误场景
业务分支错误直接返回（视图内）：

```python
return ErrorResponse(msg="未获取到数据")                     # code 默认 400
return ErrorResponse(msg="无权限删除此数据", code=403)        # 自定义业务码
return ErrorResponse(msg="参数错误", data=errors, code=400)
```

**校验失败/内部异常应抛异常而非返回 ErrorResponse**（由全局异常处理器统一转标准错误响应）：

```python
from utils.exception import APIException, AuthenticationError, PermissionDeniedError

raise APIException(message="该数据存在关联引用,无法删除")     # → 业务码 4000
raise AuthenticationError()                                  # → 业务码 4001（跳登录）
raise PermissionDeniedError()                                # → 业务码 4000
```

序列化器 `validate()` 钩子中的唯一性校验参考（对齐 DRF UniqueValidator msg 格式）：

```python
def validate(self, data):
    key = data.get("key")
    if key:
        exists = self.db.query(Dept.id).filter(Dept.key == key, Dept.id != current_id).first()
        if exists:
            from utils.exception import APIException, drf_validation_msg
            raise APIException(code=4000,
                               message=drf_validation_msg("key", "具有 关联字符 的 部门表 已存在。"))
    return data
```

## 完整视图参考（真实代码）

见 `backend/mysystem/views/dept.py`（DeptViewSet：过滤器 + 序列化器 + set_status action）。

## 注意事项

1. **SuccessResponse / DetailResponse 默认 code 为 2000**，不要传其他 code
2. **ErrorResponse 默认 code 为 400**，可自定义 code；`status` 参数可改 HTTP 状态码（一般不动，保持 200）
3. **前端判断成功条件**：`res.code === 2000`
4. **分页数据必须走 `paginate_response`（或 SuccessResponse）**，确保前端分页组件拿到 page/limit/total 结构
5. **HTTP 状态码恒 200**，不要通过 HTTP 状态码表达错误；错误一律用业务码（body.code）
6. **响应格式必须用这三个类（或 `utils.jsonResponse._json`）**，禁止直接 `return {"code": ...}` dict 或裸 JSONResponse（会丢失回环地址改写）
7. 序列化器需继承 `CustomModelSerializer`（`backend/utils/serializers.py`），声明 `model / fields / read_only_fields / required_fields`
