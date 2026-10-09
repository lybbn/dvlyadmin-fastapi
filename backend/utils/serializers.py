# -*- coding: utf-8 -*-
"""
@Remark: 自定义序列化器（对应 Django utils/serializers.py 的 CustomModelSerializer）
设计说明（与 DRF 版行为对齐）：
(1) fields="__all__" 时自动从模型列推导输出字段；Django FK(db_constraint=False) 列
    （*_id 且非 dept_belong）输出时去掉 _id 后缀（对齐 DRF PrimaryKeyRelatedField 的输出键名）
(2) 时间字段输出统一 %Y-%m-%d %H:%M:%S（对齐 CustomModelSerializer 的 DateTimeField format）
(3) get_<字段名> 方法自动作为只读计算字段（对齐 SerializerMethodField）
(4) create/update 自动写入审计字段 creator/modifier/dept_belong（对齐 CustomModelSerializer）
(5) M2M 字段通过 m2m 声明（关联表, 自键列, 目标键列）：输出主键列表，create/update 时全量重建
"""
from mysystem.models import Users
from utils.common import formatdatetime

from sqlalchemy import Boolean as SABoolean
from sqlalchemy import Integer as SAInteger

# 时间自动字段（对齐 CustomModelSerializer 的时间格式声明）
TIME_FIELDS = {"create_datetime", "update_datetime", "last_login", "read_at", "expiration"}

# DRF BooleanField.to_internal_value 的真值集合
_TRUE_VALUES = {"true", "t", "yes", "y", "1", "on"}


def _coerce_to_column_type(model, col: str, value):
    """
    对齐 DRF 字段类型系统：导入 Excel/表单时单元格值为字符串，按列类型强转
    (1) Boolean 列：'true'/'t'/'yes'/'y'/'1'/'on' → True，'false' 等 → False，'' → 跳过(None)
    (2) Integer 列：字符串数字 → int，'' → 跳过(None)
    """
    if not isinstance(value, str):
        return value
    col_type = model.__table__.columns[col].type
    if isinstance(col_type, SABoolean):
        v = value.strip().lower()
        return None if v == "" else v in _TRUE_VALUES
    if isinstance(col_type, SAInteger) and not isinstance(value, bool):
        v = value.strip()
        if v == "":
            return None
        try:
            return int(float(v)) if ("." in v or "e" in v.lower()) else int(v)
        except ValueError:
            return None
    return value


class Empty:
    """对齐 rest_framework.fields.empty"""
    pass


empty = Empty()


class CustomModelSerializer:
    """增强序列化器基类：自动审计字段 + 标准时间格式 + M2M 支持"""

    model = None                 # SQLAlchemy 模型类（子类必填）
    fields = "__all__"           # "__all__" 或字段名列表
    exclude = ()                 # fields="__all__" 时的排除字段
    read_only_fields = []        # 输入时忽略的字段（对齐 Meta.read_only_fields）
    source_fields = {}           # {"deptName": "dept.name"} 只读嵌套输出（对齐 source=）
    related_models = {}          # {"dept": Dept} source_fields 首段关联模型解析
    m2m = {}                     # {"role": (UsersRole, "users_id", "role_id")}
    extra_output_fields = []     # 声明式计算字段（对齐 SerializerMethodField，由 get_<name> 提供值）
    required_fields = []         # 对齐 DRF 必填校验（模型 blank=False 且无 default 的字段，create/update 均校验）
    request = None               # DRF serializer.request 等价
    user = None
    instance = None              # update 时由 viewset 挂载（对齐 DRF serializer.instance）

    def __init__(self, db, request=None, user=None):
        self.db = db
        self.request = request
        self.user = user

    # ================================================= #
    # ************** 字段名推导 ************** #
    # ================================================= #

    @classmethod
    def _column_names(cls):
        return {c.name for c in cls.model.__table__.columns}

    def get_all_model_fields(self):
        """对齐 CustomModelSerializer.get_all_model_fields（模型全部字段名）"""
        return sorted(self._column_names())

    def get_field_names(self):
        """输出字段名（FK 列去掉 _id 后缀，对齐 DRF 输出键名；附加 extra_output_fields）"""
        cols = self._column_names()
        if self.fields == "__all__":
            names = []
            for c in sorted(cols):
                if c.endswith("_id") and c != "dept_belong":
                    names.append(c[:-3])
                else:
                    names.append(c)
            names = [n for n in names if n not in self.exclude]
        else:
            names = list(self.fields)
        # 声明式计算字段（对齐 SerializerMethodField），不覆盖已有列名
        for extra in self.extra_output_fields:
            if extra not in names:
                names.append(extra)
        # M2M 字段名同样追加（对齐 DRF 显式声明的 m2m 序列化字段）
        for name in self.m2m:
            if name not in names:
                names.append(name)
        return names

    def _writable_field_names(self):
        """可写字段集合（排除只读/方法/source/m2m/审计自动字段）"""
        skip = set(self.read_only_fields) | set(self.source_fields.keys()) | set(self.m2m.keys())
        cols = self._column_names()
        result = []
        for name in self.get_field_names():
            if name in skip or hasattr(type(self), f"get_{name}"):
                continue
            # create_datetime 只读（对齐 CustomModelSerializer）；id 默认不可写
            if name == "create_datetime" or name == "id":
                continue
            # FK 可写字段：允许 *_id 列对应的名称（如 parent/dept/menu/creator）
            if name in cols or f"{name}_id" in cols:
                result.append(name)
        return result

    # ================================================= #
    # ************** 输出序列化 ************** #
    # ================================================= #

    def _resolve_source(self, obj, source: str):
        """解析嵌套 source（如 dept.name / parent.name），支持一层嵌套"""
        parts = source.split(".")
        if len(parts) == 1:
            return self._read_attr(obj, parts[0])
        first, rest = parts[0], ".".join(parts[1:])
        rel_value = self._read_attr(obj, first)
        if rel_value in (None, ""):
            return None
        rel_model = self.related_models.get(first)
        if rel_model is None:
            return None
        rel_obj = self.db.get(rel_model, rel_value)
        if rel_obj is None:
            return None
        return getattr(rel_obj, rest, None)

    def _read_attr(self, obj, name):
        """按 FK 输出键名规则读取对象属性（parent → parent_id）"""
        cols = self._column_names()
        if name in cols:
            return getattr(obj, name)
        if f"{name}_id" in cols:
            return getattr(obj, f"{name}_id")
        return getattr(obj, name, None)

    def _m2m_ids(self, obj, name):
        """读取 M2M 关联主键列表"""
        from sqlalchemy import select
        assoc, self_col, target_col = self.m2m[name]
        own_value = getattr(obj, "id")
        rows = self.db.execute(
            select(getattr(assoc, target_col)).where(getattr(assoc, self_col) == own_value)
        ).all()
        return [r[0] for r in rows]

    def to_representation(self, obj) -> dict:
        data = {}
        for name in self.get_field_names():
            if hasattr(type(self), f"get_{name}"):
                data[name] = getattr(self, f"get_{name}")(obj)
                continue
            if name in self.source_fields:
                data[name] = self._resolve_source(obj, self.source_fields[name])
                continue
            if name in self.m2m:
                data[name] = self._m2m_ids(obj, name)
                continue
            value = self._read_attr(obj, name)
            if name in TIME_FIELDS and value is not None:
                value = formatdatetime(value)
            data[name] = value
        return data

    def serialize(self, obj) -> dict:
        return self.to_representation(obj)

    def serialize_many(self, objs) -> list:
        return [self.to_representation(o) for o in objs]

    # ================================================= #
    # ************** 输入与保存 ************** #
    # ================================================= #

    def run_validation(self, data):
        """对齐 serializer.is_valid+validated_data：必填校验 → 子类可重写 validate() 做校验/清洗"""
        validated = dict(data or {})
        # 对齐 DRF 必填校验：缺失 → ValidationError("该字段是必填项。")，DJ handler 输出 code 4000 + ErrorDetail repr
        for f in self.required_fields:
            if f not in validated or validated[f] is None:
                from utils.exception import APIException, drf_validation_msg
                raise APIException(code=4000, message=drf_validation_msg(f, "该字段是必填项。", "required"))
        return self.validate(validated)

    def validate(self, data):
        """子类校验钩子：校验失败 raise APIException(message=...)"""
        return data

    def _apply_audit_kwargs(self, kwargs: dict) -> dict:
        """对齐 CustomModelSerializer.create：审计字段自动赋值（按真实列名写入 kwargs）"""
        cols = self._column_names()
        if self.user is not None:
            if "modifier" in cols:
                kwargs["modifier"] = self.user.id
            elif "modifier_id" in cols:
                kwargs["modifier_id"] = self.user.id
            if "creator_id" in cols:
                kwargs["creator_id"] = self.user.id
            elif "creator" in cols:
                kwargs["creator"] = self.user.id
            if "dept_belong" in cols and not kwargs.get("dept_belong", None):
                kwargs["dept_belong"] = getattr(self.user, "dept_id", None)
            elif "dept_belong_id" in cols and not kwargs.get("dept_belong_id", None):
                kwargs["dept_belong_id"] = getattr(self.user, "dept_id", None)
        return kwargs

    def create(self, validated_data):
        """创建实例（不提交，由调用方 commit/rollback）"""
        validated = dict(validated_data or {})
        cols = self._column_names()
        kwargs = {}
        for name in self._writable_field_names():
            if name not in validated:
                continue
            col = name if name in cols else f"{name}_id"
            value = validated[name]
            if col in ("create_datetime", "update_datetime") and value in ("", None):
                continue
            coerced = _coerce_to_column_type(self.model, col, value)
            if coerced is None and isinstance(value, str) and value.strip() == "":
                continue  # 空字符串不写入，保持模型默认值
            kwargs[col] = coerced
        kwargs = self._apply_audit_kwargs(kwargs)
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.flush()
        self.save_m2m(instance, validated)
        return instance

    def update(self, instance, validated_data):
        """更新实例（对齐 CustomModelSerializer.update：modifier 自动记录）"""
        validated = dict(validated_data or {})
        cols = self._column_names()
        if self.user is not None and "modifier" in cols:
            validated["modifier"] = self.user.id
        for name in self._writable_field_names():
            if name not in validated:
                continue
            col = name if name in cols else f"{name}_id"
            value = validated[name]
            if col == "update_datetime" and value in ("", None):
                continue
            coerced = _coerce_to_column_type(self.model, col, value)
            if coerced is None and isinstance(value, str) and value.strip() == "":
                continue  # 空字符串不更新
            setattr(instance, col, coerced)
        self.db.flush()
        self.save_m2m(instance, validated)
        return instance

    def save_m2m(self, instance, validated):
        """M2M 全量重建（对齐 DRF ManyRelatedField 的 save 行为）"""
        from sqlalchemy import delete
        for name, (assoc, self_col, target_col) in self.m2m.items():
            if name not in validated:
                continue
            ids = validated.get(name) or []
            self.db.execute(delete(assoc).where(getattr(assoc, self_col) == instance.id))
            for rid in ids:
                self.db.add(assoc(**{self_col: instance.id, target_col: rid}))
        self.db.flush()


def get_request_user(serializer) -> Users:
    return serializer.user
