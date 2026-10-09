# -*- coding: utf-8 -*-

"""
@Remark: 部门管理（对应 Django mysystem/views/dept.py）
"""

from sqlalchemy import select

from mysystem.models import Dept
from utils.common import get_parameter_dic
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet


class DeptFilterSet:
    """
    部门管理 过滤器（对齐 Django DeptFilterSet）
    beginAt/endAt → create_datetime 区间，name 模糊，status 精确
    """

    def __call__(self, db, request, query):
        begin_at = request.query_params.get("beginAt", None)
        if begin_at:
            query = query.where(Dept.create_datetime >= begin_at)
        end_at = request.query_params.get("endAt", None)
        if end_at:
            query = query.where(Dept.create_datetime <= end_at)
        name = request.query_params.get("name", None)
        if name:
            query = query.where(Dept.name.ilike(f"%{name}%"))
        status = request.query_params.get("status", None)
        if status is not None and status != "":
            query = query.where(Dept.status == (status.lower() in ("true", "1")))
        return query


class DeptSerializer(CustomModelSerializer):
    """
    部门-序列化器（对齐 fields="__all__" + read_only_fields=["id"]）
    name 必填（blank=False 无 default）；key unique=True → DRF UniqueValidator（排除自身）
    """

    model = Dept
    fields = "__all__"
    read_only_fields = ["id"]
    required_fields = ["name"]

    def validate(self, data):
        key = data.get("key")
        if key:
            # 对齐 DRF UniqueValidator：排除当前实例（update）；instance 由 viewset.update 挂载
            current = getattr(self, "instance", None)
            current_id = current.id if current is not None else (data.get("id") or "")
            exists = self.db.query(Dept.id).filter(Dept.key == key, Dept.id != current_id).first()
            if exists:
                from utils.exception import APIException, drf_validation_msg
                # 对齐 DJ：ValidationError → code 4000 + msg = str(ex.detail)（默认 unique 消息含 verbose_name）
                raise APIException(code=4000,
                                   message=drf_validation_msg("key", "具有 关联字符 的 部门表 已存在。"))
        return data


class DeptViewSet(CustomViewSet):
    """
    部门管理接口
    """

    model = Dept
    serializer_class = DeptSerializer
    filterset_class = DeptFilterSet()
    search_fields = ['name', 'owner', 'phone', 'email']
    import_field_dict = {
        "ID": "id",
        "部门名称": {'field': 'name', 'example': '技术部门'},
        "标识字符": {'field': 'key', 'example': 'tec'},
        "排序": {'field': 'sort', 'example': 10},
        "上级部门": "parent",
        "状态": {'field': 'status', 'example': True},
    }
    import_serializer_class = DeptSerializer

    def set_status(self):
        """禁用/启用"""
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
