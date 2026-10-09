# -*- coding: utf-8 -*-

"""
@Remark: 按钮权限管理
"""
from mysystem.models import Button
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet


class ButtonSerializer(CustomModelSerializer):
    """
    按钮权限-序列化器
    """

    model = Button
    fields = "__all__"
    read_only_fields = ["id"]


class ButtonViewSet(CustomViewSet):
    """
    按钮权限接口:
    """
    model = Button
    serializer_class = ButtonSerializer

    def get_queryset(self):
        # 对齐 Django queryset = Button.objects.all().order_by("create_datetime")（order_by 覆盖 Meta.ordering）
        query = super().get_queryset()
        return query.order_by(None).order_by(Button.create_datetime.asc())
