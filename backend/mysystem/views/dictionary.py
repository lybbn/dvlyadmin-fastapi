# -*- coding: utf-8 -*-

"""
@Remark: 字典管理
"""
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from mysystem.models import Dictionary
from utils.common import get_parameter_dic, boolValue
from utils.jsonResponse import DetailResponse, ErrorResponse, SuccessResponse, _json
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet
from application.database import get_db


class DictionaryFilterset:
    """
    过滤器（对齐 Django DictionaryFilterset）
    fields: ['id', 'label', 'status', 'parent_isnull','parent','value']
    """

    def __call__(self, db, request, query):
        params = request.query_params
        # 精确过滤字段（parent 为 Django FK 名，模型列是 parent_id，需映射；
        # 直接 getattr(Dictionary, "parent") 会 AttributeError → 500）
        for field in ("id", "label", "parent", "value"):
            v = params.get(field, None)
            if v not in (None, ""):
                col = f"{field}_id" if field == "parent" else field
                query = query.where(getattr(Dictionary, col) == v)
        status = params.get("status", None)
        if status not in (None, ""):
            query = query.where(Dictionary.status == boolValue(status))
        v = params.get("parent_isnull", None)
        if v not in (None, ""):
            # BooleanFilter(field_name='parent', lookup_expr="isnull")
            if boolValue(v):
                query = query.where(Dictionary.parent_id.is_(None))
            else:
                query = query.where(Dictionary.parent_id.is_not(None))
        return query


class DictionarySerializer(CustomModelSerializer):
    """
    字典-序列化器
    """

    model = Dictionary
    fields = "__all__"
    read_only_fields = ["id"]


class DictionaryViewSet(CustomViewSet):
    """
    字典管理接口
    list:查询
    create:新增
    update:修改
    retrieve:单例
    destroy:删除
    """
    model = Dictionary
    serializer_class = DictionarySerializer
    filterset_class = DictionaryFilterset()
    search_fields = ('label', 'value')

    def set_status(self):
        """禁用/启用"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id", "")
        query = self.filter_queryset(self.get_queryset()).where(Dictionary.id == id)
        instance = self.db.execute(query).scalars().first()
        if instance:
            instance.status = False if instance.status else True
            self.db.commit()
            return DetailResponse(data=None, msg="设置成功")
        else:
            return ErrorResponse(msg="未获取到数据")


# ================================================= #
# ************** 公开接口（免认证，对齐 authentication_classes=[]） ************** #
# ================================================= #

async def get_dictionary_info(request, db: Session = Depends(get_db)):
    """
    get:
    获取字典信息
    参数：code 分组编码（value）
    """
    code = request.query_params.get("code", "")
    if not code:
        return ErrorResponse(msg="params error")
    # 对齐 Dictionary.objects.filter(parent__value=code, status=True).order_by("sort")
    parent = db.execute(
        select(Dictionary.id).where(Dictionary.value == code)
    ).scalars().first()
    data = []
    if parent is not None:
        rows = db.execute(
            select(Dictionary).where(Dictionary.parent_id == parent, Dictionary.status == True)  # noqa: E712
            .order_by(Dictionary.sort.asc())
        ).scalars().all()
        for m in rows:
            data.append({
                'id': m.id,
                'label': m.label,
                'value': m.value
            })
    return DetailResponse(data=data)


async def get_dictionary_all(request, db: Session = Depends(get_db)):
    """获取字典（全部分组及子项，免认证）"""
    roots = db.execute(
        select(Dictionary).where(Dictionary.parent_id.is_(None), Dictionary.status == True)  # noqa: E712
        .order_by(Dictionary.sort.asc())
    ).scalars().all()
    data = []
    for instance in roots:
        children = db.execute(
            select(Dictionary.id, Dictionary.label, Dictionary.value)
            .where(Dictionary.parent_id == instance.id, Dictionary.status == True)  # noqa: E712
            .order_by(Dictionary.sort.asc())
        ).all()
        data.append({
            "id": instance.id,
            "label": instance.label,
            "value": instance.value,
            "children": [{"id": c[0], "label": c[1], "value": c[2]} for c in children],
        })
    # 对齐 SuccessResponse(data=data, msg="获取成功", total=len(data))
    return _json({"code": 2000, "msg": "获取成功", "data": data, "total": len(data)})
