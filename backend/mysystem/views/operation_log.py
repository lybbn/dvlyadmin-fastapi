# -*- coding: utf-8 -*-

"""
@Remark: 操作日志管理
"""
from mysystem.models import OperationLog
from utils.jsonResponse import ErrorResponse, SuccessResponse
from utils.serializers import CustomModelSerializer
from utils.pagination import paginate_queryset, paginate_response
from utils.viewset import CustomViewSet


class OperationLogTimeFilter:
    """
    日志管理 简单过滤器
    """

    def __call__(self, db, request, query):
        params = request.query_params
        begin_at = params.get("beginAt", None)
        if begin_at:
            query = query.where(OperationLog.create_datetime >= begin_at)
        end_at = params.get("endAt", None)
        if end_at:
            query = query.where(OperationLog.create_datetime <= end_at)
        # 模糊搜索
        for param, field in (("req_modular", "req_modular"), ("req_path", "req_path"),
                             ("req_ip", "req_ip"), ("req_os", "req_os"), ("req_body", "req_body")):
            v = params.get(param, None)
            if v:
                query = query.where(getattr(OperationLog, field).ilike(f"%{v}%"))
        # 注意：Django 版 req_method 过滤器误写 field_name='re_method'（不存在字段），
        # 前端实际不传该参数；此处跳过不实现
        v = params.get("req_method", None)
        del v
        return query


class OperationLogSerializer(CustomModelSerializer):
    """
    操作日志-序列化器
    """

    model = OperationLog
    fields = "__all__"
    read_only_fields = ["id"]


class OperationLogViewSet(CustomViewSet):
    """
    操作日志接口
    list:查询
    create:新增
    update:修改
    retrieve:单例
    destroy:删除
    """
    model = OperationLog
    serializer_class = OperationLogSerializer
    filterset_class = OperationLogTimeFilter()
    search_fields = ('req_modular', 'req_path', 'req_ip', 'req_os', 'req_body', 'creator_name')

    def getOwnerLogs(self):
        user = self.user
        query = self.filter_queryset(self.get_queryset()).where(OperationLog.creator_id == user.id)
        serializer = self.get_serializer(OperationLogSerializer)
        items, total, page, limit = paginate_queryset(self.db, self.request, query)
        data = serializer.serialize_many(items)
        return paginate_response(self.request, data, total, page, limit)

    def deletealllogs(self):
        if self.user.is_superuser:
            self.db.query(OperationLog).delete()
            self.db.commit()
            return SuccessResponse(msg="清空成功")
        return ErrorResponse(msg="您没有权限执行此操作，需要超级管理员权限")
