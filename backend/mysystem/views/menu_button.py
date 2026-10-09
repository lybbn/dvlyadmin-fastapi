# -*- coding: utf-8 -*-

"""
@Remark: 菜单按钮管理
"""
from mysystem.models import MenuButton, Menu, RoleMenuButtonPermission, get_user_role_ids
from utils.common import get_parameter_dic
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet


class MenuButtonSerializer(CustomModelSerializer):
    """
    菜单按钮-序列化器
    """

    model = MenuButton
    fields = "__all__"
    read_only_fields = ["id"]


class MenuButtonViewSet(CustomViewSet):
    """
    菜单按钮接口:
    """
    model = MenuButton
    serializer_class = MenuButtonSerializer
    filterset_fields = ['menu']

    def get_queryset(self):
        # 对齐 Django queryset = MenuButton.objects.all().order_by("id")（order_by 覆盖 Meta.ordering）
        return super().get_queryset().order_by(None).order_by(MenuButton.id.asc())

    def menu_button_permission(self):
        """
        获取根据角色获取按钮权限
        """
        if self.user.is_superuser:
            # 对齐 Django MenuButton.objects.values_list('value', flat=True)
            # （Meta.ordering = ('-name',) → 按 name 倒序）
            values = self.db.execute(
                MenuButton.__table__.select().with_only_columns(MenuButton.value)
                .order_by(MenuButton.name.desc())
            ).all()
            data = [v[0] for v in values]
        else:
            role_id = get_user_role_ids(self.db, self.user.id)
            # 对齐 RoleMenuButtonPermission.objects.filter(role__in=role_id)
            #   .values_list('menu_button__value', flat=True).distinct()
            from sqlalchemy import select
            rows = self.db.execute(
                select(MenuButton.value)
                .join(RoleMenuButtonPermission, RoleMenuButtonPermission.menu_button_id == MenuButton.id)
                .where(RoleMenuButtonPermission.role_id.in_(role_id))
                .distinct()
            ).all()
            data = [v[0] for v in rows]
        return DetailResponse(data=data)

    def batch_generate(self):
        """自动批量生成增删改查详情 按钮权限"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        menu_id = reqData.get("menu", "")
        baseapi = reqData.get("baseapi", "")  # 若不提供基础api前缀，则默认为组件名
        if not menu_id:
            return ErrorResponse(msg="请提供要添加的菜单")
        ins = self.db.get(Menu, menu_id)
        if not ins:
            return ErrorResponse(msg="无此菜单")
        if not baseapi:
            baseapi = f'/api/{ins.component_name}/'
        data_list = [
            {'menu': ins.id, 'name': '新增', 'value': f'{ins.component_name}:Create', 'api': f'{baseapi}', 'method': 1},
            {'menu': ins.id, 'name': '删除', 'value': f'{ins.component_name}:Delete', 'api': f'{baseapi}{{id}}/', 'method': 3},
            {'menu': ins.id, 'name': '编辑', 'value': f'{ins.component_name}:Update', 'api': f'{baseapi}{{id}}/', 'method': 2},
            {'menu': ins.id, 'name': '查询', 'value': f'{ins.component_name}:Search', 'api': f'{baseapi}', 'method': 0},
            {'menu': ins.id, 'name': '详情', 'value': f'{ins.component_name}:Detail', 'api': f'{baseapi}{{id}}/', 'method': 0},
            {'menu': ins.id, 'name': '导出', 'value': f'{ins.component_name}:Export', 'api': f'{baseapi}export_data/', 'method': 1},
        ]
        serializer = self.get_serializer(MenuButtonSerializer)
        for item in data_list:
            validated = serializer.run_validation(item)
            serializer.create(validated)
        self.db.commit()
        return DetailResponse(msg="批量生成成功")
