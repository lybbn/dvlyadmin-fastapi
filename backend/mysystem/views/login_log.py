# -*- coding: utf-8 -*-

"""
@Remark: 登录日志管理
"""
from sqlalchemy import or_

from mysystem.models import LoginLog
from utils.jsonResponse import ErrorResponse, SuccessResponse
from utils.serializers import CustomModelSerializer
from utils.pagination import paginate_queryset, paginate_response
from utils.viewset import CustomViewSet


class LoginLogTimeFilter:
    """
    登录日志 简单过滤器
    """

    def __call__(self, db, request, query):
        params = request.query_params
        begin_at = params.get("beginAt", None)
        if begin_at:
            query = query.where(LoginLog.create_datetime >= begin_at)
        end_at = params.get("endAt", None)
        if end_at:
            query = query.where(LoginLog.create_datetime <= end_at)
        # 模糊搜索
        for field in ("username", "ip"):
            v = params.get(field, None)
            if v:
                query = query.where(getattr(LoginLog, field).ilike(f"%{v}%"))
        return query


class LoginLogSerializer(CustomModelSerializer):
    """
    登录日志-序列化器
    """

    model = LoginLog
    fields = "__all__"
    read_only_fields = ["id"]


class LoginLogViewSet(CustomViewSet):
    """
    登录日志接口
    list:查询
    create:新增
    update:修改
    retrieve:单例
    destroy:删除
    """
    model = LoginLog
    serializer_class = LoginLogSerializer
    filterset_class = LoginLogTimeFilter()
    search_fields = ('ip', 'username')

    def getOwnerLogs(self):
        user = self.user
        query = self.filter_queryset(self.get_queryset())
        # 对齐 queryset.filter(Q(creator=user) | Q(username=user.username)).distinct()
        query = query.where(or_(LoginLog.creator_id == user.id, LoginLog.username == user.username))
        serializer = self.get_serializer(LoginLogSerializer)
        items, total, page, limit = paginate_queryset(self.db, self.request, query)
        data = serializer.serialize_many(items)
        return paginate_response(self.request, data, total, page, limit)

    def deletealllogs(self):
        if self.user.is_superuser:
            self.db.query(LoginLog).delete()
            self.db.commit()
            return SuccessResponse(msg="清空成功")
        return ErrorResponse(msg="您没有权限执行此操作，需要超级管理员权限")
