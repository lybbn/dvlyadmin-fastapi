# -*- coding: utf-8 -*-
"""
@Remark: 自定义视图集（对应 Django utils/viewset.py 的 CustomModelViewSet）
FastAPI 实现方式：
(1) CustomViewSet 为声明式基类，通过 register(router) 生成与 DRF SimpleRouter 完全一致的路由：
    GET/POST /          list/create
    GET/PUT/PATCH/DELETE /{pk}/    retrieve/update/partial_update/destroy(支持 1,2,3 批量)
    DELETE /multiple_delete/       批量删除
    POST /export_data/  /import_data/  /download_template/   导入导出
    GET /field_permission/        列权限查询
(2) 请求链：JWT 认证 → CustomPermission（step_permission 豁免）→ 数据权限过滤 → CRUD
(3) 自定义 action（set_status 等）由 mysystem/urls.py 手工注册（与 Django 版一致）
"""
import time
import random
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.orm import Session

from application.database import get_db
from mysystem.models import Users
from utils.common import get_parameter_dic
from utils.exception import APIException
from utils.field_permission import (apply_field_permissions_to_input, apply_field_permissions_to_output,
                                    get_field_permissions)
from utils.filters import (DataLevelPermissionsFilter, apply_filterset, apply_ordering, apply_search)
from utils.jsonResponse import DetailResponse, ErrorResponse, SuccessResponse, _json
from utils.pagination import paginate_queryset, paginate_response
from utils.permission import get_current_user, require_api_permission
from utils.security import make_password  # noqa: F401 子类视图常需

logger = logging.getLogger(__name__)


def apply_cascade(db: Session, model, ids: list) -> None:
    """
    对齐 Django queryset.delete() 的 Collector 级联删除（CASCADE_RULES 声明见 mysystem/models.py）：
    - protect 项：存在引用行 → 抛 APIException（对齐 DJ on_delete=PROTECT 的保护语义，
      DJ 端 ProtectedError 未捕获返回 500，此处按本端约定返回 code 4000，属接受差异）
    - cascade 项：先递归处理子表（链式与自关联子树自动展开），再删除各层主体行
    """
    if not ids:
        return
    from mysystem.models import CASCADE_RULES, get_cascade_model
    rules = CASCADE_RULES.get(model.__name__)
    if not rules:
        # 无规则模型（Button/Dictionary 主体等）行为与 DJ 一致：只删自身
        db.execute(delete(model).where(model.id.in_(ids)).execution_options(synchronize_session=False))
        return
    # PROTECT 校验（对齐 on_delete=PROTECT）
    for ref_name, col in rules.get("protect", []):
        ref_model = get_cascade_model(ref_name)
        n = db.execute(
            select(ref_model.id).where(getattr(ref_model, col).in_(ids)).limit(1)
        ).first()
        if n:
            raise APIException(code=4000, message="删除失败:该数据存在关联引用,无法删除")
    # CASCADE：递归子表 → 删主体
    for child_name, col in rules.get("cascade", []):
        if child_name.startswith("@table:"):
            # DJ m2m 自动生成表（本端无模型类）：裸 SQL 删除
            db.execute(
                text(f"DELETE FROM {child_name[7:]} WHERE {col} IN :ids").bindparams(
                    bindparam("ids", expanding=True)),
                {"ids": ids},
            )
            continue
        child_model = get_cascade_model(child_name)
        child_ids = [r[0] for r in db.execute(
            select(child_model.id).where(getattr(child_model, col).in_(ids))
        ).all()]
        if child_ids:
            apply_cascade(db, child_model, child_ids)
    db.execute(delete(model).where(model.id.in_(ids)).execution_options(synchronize_session=False))


class CustomViewSet:
    """自定义视图集基类（对应 CustomModelViewSet）"""

    model = None
    queryset = None                # 可覆盖（None 时全表 select(model)）
    serializer_class = None
    create_serializer_class = None
    update_serializer_class = None
    export_serializer_class = None
    import_serializer_class = None
    filterset_fields = ()
    filterset_class = None         # 可调用 (db, request, query) -> query
    search_fields = ()
    ordering_fields = "__all__"
    values_queryset = None
    step_permission = False        # 视图级权限豁免（对齐 view.step_permission）
    # 导入导出配置（对齐 ImportExportMixin）
    export_field_dict = {}
    import_field_dict = {}
    import_image_fields = []
    show_image = True
    export_column_width = 80
    file_name = "ly" + time.strftime('%Y%m%d%H%M%S') + str(random.randint(10, 99)) + ".xlsx"
    save_dir = "systemexport"

    # ---------- 上下文 ----------

    def __init__(self, request: Request, db: Session, user: Users):
        self.request = request
        self.db = db
        self.user = user
        self.action = None

    def get_request_data(self) -> dict:
        """对齐 request.data（JSON body，由中间件依赖预解析到 request.state.body）"""
        return getattr(self.request.state, "body", None) or {}

    def get_serializer(self, serializer_class=None):
        serializer_class = serializer_class or self.serializer_class
        return serializer_class(self.db, request=self.request, user=self.user)

    def _output_serializer(self):
        if self.action == "create" and self.create_serializer_class:
            return self.create_serializer_class
        if self.action in ("update", "partial_update") and self.update_serializer_class:
            return self.update_serializer_class
        if self.action == "export_data" and self.export_serializer_class:
            return self.export_serializer_class
        if self.action == "import_data" and self.import_serializer_class:
            return self.import_serializer_class
        return self.serializer_class

    def get_queryset(self):
        """基础查询（含模型默认排序，对齐 Django Meta.ordering）"""
        if getattr(self, 'values_queryset', None):
            return self.values_queryset
        if self.queryset is not None:
            query = self.queryset() if callable(self.queryset) else self.queryset
        else:
            query = select(self.model)
        default_ordering = getattr(self.model, "__default_ordering__", None)
        if default_ordering:
            order_cols = []
            for term in default_ordering:
                desc = term.startswith("-")
                col = getattr(self.model, term[1:] if desc else term)
                order_cols.append(col.desc() if desc else col.asc())
            if order_cols:
                query = query.order_by(*order_cols)
        return query

    def filter_queryset(self, query):
        """对齐 CustomModelViewSet.filter_queryset：数据权限 → filterset → search → ordering"""
        # extra_filter_backends: DataLevelPermissionsFilter
        query = DataLevelPermissionsFilter.apply(
            self.db, self.request, self.user, query, self.model,
            path_pk=self.request.path_params.get("pk"),
        )
        # filterset
        query = apply_filterset(self.db, self.request, query, self.model,
                                self.filterset_fields, self.filterset_class)
        # search
        query = apply_search(self.request, query, self.model, self.search_fields)
        # ordering
        query = apply_ordering(self.request, query, self.model, self.ordering_fields)
        return query

    def get_object(self):
        """对齐 get_object_or_404：不存在 → 404；类型不匹配 → APIException(4000)"""
        pk = self.request.path_params.get("pk")
        try:
            instance = self.db.get(self.model, pk)
        except (TypeError, ValueError):
            raise APIException(message='该对象不存在或者无访问权限')
        if instance is None:
            from starlette.exceptions import HTTPException as StarletteHTTPException
            raise StarletteHTTPException(404)
        return instance

    # ---------- 动作实现（方法名与 DRF 一致） ----------

    def list(self):
        self.action = "list"
        query = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(self._output_serializer())
        items, total, page, limit = paginate_queryset(self.db, self.request, query)
        data = [apply_field_permissions_to_output(self._field_permissions(), d)
                for d in serializer.serialize_many(items)]
        return paginate_response(self.request, data, total, page, limit)

    def create(self):
        self.action = "create"
        data = self.get_request_data()
        serializer = self.get_serializer(self._output_serializer())
        validated = serializer.run_validation(data)
        validated = apply_field_permissions_to_input(self._field_permissions(), validated, "create")
        instance = serializer.create(validated)
        self.db.commit()
        self.db.refresh(instance)
        out = serializer.serialize(instance)
        out = apply_field_permissions_to_output(self._field_permissions(), out)
        return DetailResponse(data=out, msg="新增成功")

    def retrieve(self):
        self.action = "retrieve"
        instance = self.get_object()
        serializer = self.get_serializer(self._output_serializer())
        data = serializer.serialize(instance)
        data = apply_field_permissions_to_output(self._field_permissions(), data)
        return DetailResponse(data=data, msg="获取成功")

    def update(self, partial=False):
        self.action = "partial_update" if partial else "update"
        instance = self.get_object()
        data = self.get_request_data()
        serializer = self.get_serializer(self._output_serializer())
        serializer.instance = instance  # validate 钩子可用（对齐 DRF serializer.instance，如 unique 排除自身）
        validated = serializer.run_validation(data)
        validated = apply_field_permissions_to_input(self._field_permissions(), validated, self.action)
        serializer.update(instance, validated)
        self.db.commit()
        self.db.refresh(instance)
        out = serializer.serialize(instance)
        out = apply_field_permissions_to_output(self._field_permissions(), out)
        return DetailResponse(data=out, msg="更新成功")

    def destroy(self):
        """批量删除 /1,2,3/（对齐 get_object_list + perform_destroy）"""
        self.action = "destroy"
        pk = self.request.path_params.get("pk")
        ids = str(pk).split(',')
        query = self.filter_queryset(self.get_queryset()).where(self.model.id.in_(ids))
        instances = self.db.execute(query).scalars().all()
        # 对齐 Django queryset.delete() 的 Collector 级联删除（on_delete=CASCADE/PROTECT）
        apply_cascade(self.db, self.model, [ins.id for ins in instances])
        self.db.commit()
        return DetailResponse(data=[], msg="删除成功")

    def multiple_delete(self):
        """新的批量删除方法（对齐 multiple_delete：直接 get_queryset，无数据权限过滤）"""
        self.action = "multiple_delete"
        request_data = self.get_request_data()
        keys = request_data.get('keys', None)
        if keys:
            query = self.get_queryset().where(self.model.id.in_(keys))
            instances = self.db.execute(query).scalars().all()
            # 对齐 DJ get_queryset().filter(id__in=keys).delete() 的级联删除
            apply_cascade(self.db, self.model, [ins.id for ins in instances])
            self.db.commit()
            return SuccessResponse(data=[], msg="删除成功")
        else:
            return ErrorResponse(msg="未获取到keys字段")

    # ---------- 字段权限 ----------

    def _field_permissions(self) -> dict:
        """当前模型字段权限（model 类名，对齐 serializer.Meta.model.__name__）"""
        if self.serializer_class is None:
            return {}
        model_name = self.model.__name__
        try:
            return get_field_permissions(self.db, self.request, self.user, model_name)
        except Exception:
            return {}

    def field_permission(self):
        """字段权限查询接口 GET /field_permission/"""
        self.action = "field_permission"
        permissions = self._field_permissions()
        return DetailResponse(data=permissions)

    # ================================================= #
    # ************** 路由注册 ************** #
    # ================================================= #

    @classmethod
    def register(cls, router: APIRouter, prefix: str = ""):
        """
        生成与 DRF SimpleRouter + ImportExportMixin + FieldPermissionMixin 一致的路由
        @param prefix: 资源前缀（对齐 system_url.register(r'dept', DeptViewSet) 的 r'dept'）
        """
        view = cls
        p = "/" + prefix.strip("/") if prefix else ""
        # 登记 prefix → model 映射（日志中间件 req_modular 回退取 verbose_name 用，
        # 对齐 Django get_verbose_name(view_func.cls.queryset)）
        try:
            from application import settings as _settings
            if prefix:
                _settings.API_VIEW_MODEL_MAP[prefix.strip("/")] = cls.model
        except Exception:
            pass

        def _guard(step_permission: bool = False):
            def dep(request: Request, db: Session = Depends(get_db),
                    user: Users = Depends(get_current_user)):
                if not step_permission:
                    require_api_permission(request, db, user)
                return user
            return dep

        # 注意：自定义 action（multiple_delete/export_data 等）必须先于 /{pk}/ 注册，
        # 与 Django urls.py 中 re_path 先于 router 注册的顺序一致

        async def _parse_body(request: Request, call_next=None):
            """预解析 JSON body 到 request.state.body"""
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                ct = request.headers.get("content-type", "")
                if "application/json" in ct:
                    try:
                        request.state.body = await request.json()
                    except Exception:
                        request.state.body = {}
                else:
                    try:
                        request.state.body = await request.json()
                    except Exception:
                        request.state.body = {}
            else:
                request.state.body = {}
            return request.state.body

        # ---- multiple_delete (DELETE) ----
        @router.delete(f"{p}/multiple_delete/", dependencies=[Depends(_parse_body)])
        def _multiple_delete(request: Request, db: Session = Depends(get_db),
                             user: Users = Depends(_guard())):
            return view(request, db, user).multiple_delete()

        # ---- export_data / import_data / download_template (POST) ----
        @router.post(f"{p}/export_data/", dependencies=[Depends(_parse_body)])
        def _export_data(request: Request, db: Session = Depends(get_db),
                         user: Users = Depends(_guard())):
            from utils.export_import_mixin import export_data_action
            return export_data_action(view(request, db, user))

        @router.post(f"{p}/import_data/")
        async def _import_data(request: Request, db: Session = Depends(get_db),
                               user: Users = Depends(_guard())):
            from utils.export_import_mixin import import_data_action
            state = await _prepare_upload(request)
            return import_data_action(view(request, db, user), state)

        @router.post(f"{p}/download_template/")
        def _download_template(request: Request, db: Session = Depends(get_db),
                               user: Users = Depends(_guard())):
            from utils.export_import_mixin import download_template_action
            return download_template_action(view(request, db, user))

        # ---- field_permission (GET) ----
        @router.get(f"{p}/field_permission/")
        def _field_permission(request: Request, db: Session = Depends(get_db),
                              user: Users = Depends(_guard())):
            return view(request, db, user).field_permission()

        # ---- 标准 CRUD ----
        @router.get(f"{p}/", dependencies=[Depends(_parse_body)])
        def _list(request: Request, db: Session = Depends(get_db),
                  user: Users = Depends(_guard())):
            return view(request, db, user).list()

        @router.post(f"{p}/", dependencies=[Depends(_parse_body)])
        def _create(request: Request, db: Session = Depends(get_db),
                    user: Users = Depends(_guard())):
            return view(request, db, user).create()

        @router.get(f"{p}/{{pk}}/")
        def _retrieve(request: Request, db: Session = Depends(get_db),
                      user: Users = Depends(_guard())):
            return view(request, db, user).retrieve()

        @router.put(f"{p}/{{pk}}/", dependencies=[Depends(_parse_body)])
        def _update(request: Request, db: Session = Depends(get_db),
                    user: Users = Depends(_guard())):
            return view(request, db, user).update(partial=False)

        @router.patch(f"{p}/{{pk}}/", dependencies=[Depends(_parse_body)])
        def _partial_update(request: Request, db: Session = Depends(get_db),
                            user: Users = Depends(_guard())):
            return view(request, db, user).update(partial=True)

        @router.delete(f"{p}/{{pk}}/")
        def _destroy(request: Request, db: Session = Depends(get_db),
                     user: Users = Depends(_guard())):
            return view(request, db, user).destroy()

    @classmethod
    def register_action(cls, router: APIRouter, path: str, methods: list, action_name: str,
                        step_permission: bool = False, pk_in_path: bool = False):
        """
        注册自定义 action（对应 Django urls.py 的 re_path('xxx/set_status/', ViewSet.as_view({...}))）
        视图方法签名：def set_status(self) -> JSONResponse（从 self.request/self.db/self.user 取上下文）
        """
        view = cls

        def _guard():
            def dep(request: Request, db: Session = Depends(get_db),
                    user: Users = Depends(get_current_user)):
                if not step_permission:
                    require_api_permission(request, db, user)
                return user
            return dep

        async def _parse_body(request: Request):
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                try:
                    request.state.body = await request.json()
                except Exception:
                    request.state.body = {}
            else:
                request.state.body = {}
            return request.state.body

        method_map = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH"}
        fastapi_methods = [method_map[m.lower()] for m in methods]

        def make_handler():
            def handler(request: Request, db: Session = Depends(get_db),
                        user: Users = Depends(_guard())):
                vs = view(request, db, user)
                vs.action = action_name
                return getattr(vs, action_name)()
            return handler

        # 归一化前导斜杠（Django re_path('dept/set_status/') → FastAPI '/dept/set_status/'）
        normalized_path = "/" + path.lstrip("/")
        deps = [Depends(_parse_body)] if any(m in ("POST", "PUT", "PATCH", "DELETE") for m in fastapi_methods) else []
        router.add_api_route(normalized_path, make_handler(), methods=fastapi_methods,
                             dependencies=deps)


async def _prepare_upload(request: Request):
    """解析 multipart 上传（import_data 用）：文件与表单字段"""
    from starlette.datastructures import UploadFile
    form = await request.form()
    state = {"files": {}, "form": {}}
    for key in form.keys():
        value = form[key]
        if isinstance(value, UploadFile):
            content = await value.read()
            state["files"][key] = {"name": value.filename, "content": content}
        else:
            state["form"][key] = value
    request.state.body = state["form"]
    request.state.files = state["files"]
    return state
