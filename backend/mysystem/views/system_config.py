# -*- coding: utf-8 -*-
"""
@Remark: 系统配置（对应 Django mysystem/views/system_config.py）
阶段1：getSystemConfig 等函数与 getconfig 公开接口；
阶段3：SystemConfigViewSet CRUD（sysconfig 系列）。
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from application.database import get_db
from mysystem.models import SystemConfig
from utils.common import ast_convert, boolValue, safe_parse_json, get_parameter_dic
from utils.jsonResponse import DetailResponse
from utils.models import get_all_models_objects
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet
from utils.exception import APIException

system_config_router = APIRouter()

# 对齐 Django SystemConfig.CHOICE_FORM_ITEM_TYPE_LIST
FORM_ITEM_TYPE_CHOICES = {
    0: "text",
    1: "datetime",
    2: "date",
    3: "textarea",
    4: "select",
    5: "checkbox",
    6: "radio",
    7: "image",
    8: "singlefile",
    9: "switch",
    10: "number",
    11: "array",
    12: "images",
    13: "time",
    14: "file",
}


@system_config_router.get("/getconfig/")
def get_config(db: Session = Depends(get_db)):
    """获取系统配置（对应 GetSystemConfigSettingsView，公开接口）"""
    data = getSystemConfig(db)
    return DetailResponse(data=data)


def getSystemConfig(db: Session, key="base", group=True):
    """
    当group=False时，表示查询具体的一个key的信息，这里的key用 base.logo 即 父key.子key 的方式访问
    当group=True时，表示查询一个parent 为指定key的组信息
    """
    parent = aliased(SystemConfig)
    if group:
        queryset = db.execute(
            select(SystemConfig.value, SystemConfig.key, SystemConfig.form_item_type)
            .join(parent, SystemConfig.parent_id == parent.id)
            .where(parent.key == key)
        ).all()
    else:
        keys = key.split('.')  # 拆分成 ["a", "b"]
        if len(keys) == 2:
            queryset = db.execute(
                select(SystemConfig.value, SystemConfig.key, SystemConfig.form_item_type)
                .join(parent, SystemConfig.parent_id == parent.id)
                .where(parent.key == keys[0], SystemConfig.key == keys[1])
            ).all()
        elif len(keys) == 1:
            queryset = db.execute(
                select(SystemConfig.value, SystemConfig.key, SystemConfig.form_item_type)
                .where(SystemConfig.key == key)
            ).all()
        else:
            raise Exception("key格式错误")
    data = {}
    if queryset:
        for m in queryset:
            value, config_key, form_item_type = m
            if form_item_type == 9:
                value = boolValue(value)
            data[config_key] = value
    return data


# ================================================= #
# ************** SystemConfigViewSet（阶段3） ************** #
# ================================================= #

class SystemConfigFilter:
    """
    过滤器（对齐 SystemConfigFilter：id/parent/status 精确 + parent__isnull）
    """

    def __call__(self, db, request, query):
        params = request.query_params
        for field in ("id", "parent"):
            v = params.get(field, None)
            if v not in (None, ""):
                query = query.where(getattr(SystemConfig, f"{field}_id" if field == "parent" else field) == v)
        status = params.get("status", None)
        if status not in (None, ""):
            query = query.where(SystemConfig.status == boolValue(status))
        v = params.get("parent__isnull", None)
        if v not in (None, ""):
            if boolValue(v):
                query = query.where(SystemConfig.parent_id.is_(None))
            else:
                query = query.where(SystemConfig.parent_id.is_not(None))
        return query


class SystemConfigSerializer(CustomModelSerializer):
    """
    系统配置-序列化器（rule/setting/data_options 输出 ast_convert）
    """

    model = SystemConfig
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["form_item_type_label"]

    def get_form_item_type_label(self, obj):
        # 对齐 form_item_type_label = CharField(source='get_form_item_type_display')
        return FORM_ITEM_TYPE_CHOICES.get(obj.form_item_type)

    def to_representation(self, obj) -> dict:
        ret = super().to_representation(obj)
        ret['rule'] = ast_convert(ret['rule'])
        ret['setting'] = ast_convert(ret['setting'])
        ret['data_options'] = ast_convert(ret['data_options'])
        return ret


def _json_encode_config_fields(data: dict) -> dict:
    """对齐 JSONField 入参：dict/list → json 字符串存储（Django 由 JSONField 自动 str 化）"""
    for f in ("rule", "data_options", "setting"):
        if f in data and isinstance(data[f], (dict, list)):
            data[f] = json.dumps(data[f], ensure_ascii=False)
    return data


class SystemConfigCreateSerializer(SystemConfigSerializer):
    """
    系统配置-新增时使用-序列化器
    """

    def validate(self, data):
        data = _json_encode_config_fields(data)
        # 验证key是否允许重复：parent为空时不允许重复,反之允许
        value = data.get("key")
        if value:
            exists = self.db.query(SystemConfig.id).filter(
                SystemConfig.key == value, SystemConfig.parent_id.is_(None)).first()
            if exists:
                raise APIException(message='已存在相同变量名')
        return data


class SystemConfigChildrenSerializer(SystemConfigSerializer):
    """
    系统配置子级-序列化器（children 嵌套 + switch 布尔 + apiWhiteList JSON）
    """
    extra_output_fields = SystemConfigSerializer.extra_output_fields + ["children"]

    def get_children(self, obj):
        # 对齐 DJ：children 用 SystemConfigSerializer 序列化（无 children 键、无 switch 布尔转换）
        rows = self.db.execute(
            select(SystemConfig).where(SystemConfig.parent_id == obj.id)
            .order_by(SystemConfig.sort.asc())  # 对齐 Meta.ordering=("sort",)
        ).scalars().all()
        return SystemConfigSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)

    def to_representation(self, instance) -> dict:
        ret = super().to_representation(instance)
        if ret.get('form_item_type') == 9:
            ret['value'] = boolValue(ret['value'])
        if ret.get('key') == "apiWhiteList":
            ret['value'] = safe_parse_json(ret['value'])
        return ret


class SystemConfigUpdateSerializer(SystemConfigSerializer):
    """
    系统配置-编辑时使用-序列化器（key/title 非必填；key 唯一校验排除自身）
    """

    def validate(self, data):
        data = _json_encode_config_fields(data)
        ins = getattr(self, "_instance", None)
        value = data.get("key")
        if value and ins is not None:
            exists = self.db.query(SystemConfig.id).filter(
                SystemConfig.key == value,
                SystemConfig.parent_id.is_(None),
                SystemConfig.id != ins.id).first()
            if exists:
                raise APIException(message='已存在相同变量名')
        return data


class SystemConfigViewSet(CustomViewSet):
    """
    系统配置接口
    """
    model = SystemConfig
    serializer_class = SystemConfigChildrenSerializer
    create_serializer_class = SystemConfigCreateSerializer
    update_serializer_class = SystemConfigUpdateSerializer
    filterset_class = SystemConfigFilter()

    def get_queryset(self):
        # 对齐 SystemConfig.objects.order_by('sort', 'create_datetime')（显式排序覆盖 Meta.ordering）
        return (super().get_queryset()
                .order_by(None)
                .order_by(SystemConfig.sort.asc(), SystemConfig.create_datetime.asc()))

    def update(self, partial=False):
        """对齐 Django 自定义 update：get_object → 校验（UpdateSerializer）→ ChildrenSerializer 输出"""
        instance = self.get_object()
        data = self.get_request_data()
        serializer = SystemConfigUpdateSerializer(self.db, request=self.request, user=self.user)
        serializer._instance = instance
        validated = serializer.run_validation(data)
        validated = self._apply_field_perm_input(validated, "update" if not partial else "partial_update")
        serializer.update(instance, validated)
        self.db.commit()
        self.db.refresh(instance)
        out = SystemConfigChildrenSerializer(self.db, request=self.request, user=self.user).serialize(instance)
        return DetailResponse(data=out, msg="更新成功")

    def _apply_field_perm_input(self, validated, action_name):
        from utils.field_permission import apply_field_permissions_to_input
        return apply_field_permissions_to_input(self._field_permissions(), validated, action_name)

    def save_content(self):
        """保存配置（body 为 [{id, value, ...}] 批量 upsert）"""
        body = self.get_request_data()
        if not isinstance(body, list):
            body = [body]
        serializer = SystemConfigCreateSerializer(self.db, request=self.request, user=self.user)
        for data in body:
            obj_id = data.get('id')
            instance_obj = self.db.get(SystemConfig, obj_id) if obj_id else None
            validated = serializer.run_validation(dict(data))
            if instance_obj is None:
                serializer.create(validated)
            else:
                serializer.update(instance_obj, validated)
        self.db.commit()
        return DetailResponse(msg="保存成功")

    def get_models_info_list(self):
        """
        获取所有的model及字段信息
        """
        res = [e.get('table') for e in get_all_models_objects().values()]
        return DetailResponse(msg="获取成功", data=res)
