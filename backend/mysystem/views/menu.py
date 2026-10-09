# -*- coding: utf-8 -*-

"""
@Remark: 菜单模块
"""
from sqlalchemy import select

from mysystem.models import Menu, MenuButton, RoleMenuPermission, get_user_role_ids, Button
from utils.common import get_parameter_dic, ast_convert
from utils.jsonResponse import DetailResponse, ErrorResponse, SuccessResponse
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet
from mysystem.views.menu_button import MenuButtonSerializer


class MenuSerializer(CustomModelSerializer):
    """
    菜单表的简单序列化器
    """

    model = Menu
    fields = "__all__"
    read_only_fields = ["id"]


class MenuCreateSerializer(CustomModelSerializer):
    """
    菜单表的创建序列化器（对齐 name required=False，本序列化器不做必填校验，无需特殊处理）
    新建菜单后自动生成 CRUD 按钮权限（对齐 DJ mysystem/signals.py 的 post_save 信号）
    """

    model = Menu
    fields = "__all__"
    read_only_fields = ["id"]

    # 对齐 signals.py：CRUD_BUTTON 与 METHOD_CHOICES（0GET/1POST/2PUT/3DELETE）
    CRUD_BUTTON = ['Create', 'Delete', 'Update', 'Retrieve', 'Search']
    METHOD_CHOICES = [1, 3, 2, 0, 0]

    def create(self, validated_data):
        instance = super().create(validated_data)
        # 对齐信号逻辑：created 且 isautopm 时为菜单自动添加查询/删除/修改/新增/详情按钮
        if instance.isautopm:
            buttons = self.db.execute(select(Button)).scalars().all()
            for btn in buttons:
                if btn.value in self.CRUD_BUTTON:
                    # api 对齐 DJ CharField 无 default 落库空字符串；method 按映射取值
                    self.db.add(MenuButton(
                        menu_id=instance.id, name=btn.name, value=btn.value,
                        api="", method=self.METHOD_CHOICES[self.CRUD_BUTTON.index(btn.value)],
                    ))
            self.db.flush()
        return instance


class MenuTreeSerializer(CustomModelSerializer):
    """
    菜单表的树形序列化器（children 递归 + menu_buttons 嵌套 + menu_buttons_name）
    """

    model = Menu
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["children", "menu_buttons_name", "menu_buttons"]

    def get_children(self, obj):
        # 对齐 Menu.objects.filter(parent=instance.id).filter(status=1)（Meta.ordering=('sort',)）
        rows = self.db.execute(
            select(Menu).where(Menu.parent_id == obj.id, Menu.status == True)  # noqa: E712
            .order_by(Menu.sort.asc())
        ).scalars().all()
        if not rows:
            return None
        return self.serialize_many(rows)

    def get_menu_buttons_name(self, obj):
        # 对齐 MenuButton Meta.ordering=('-name',)
        rows = self.db.execute(
            select(MenuButton.name).where(MenuButton.menu_id == obj.id)
            .order_by(MenuButton.name.desc())
        ).all()
        return [r[0] for r in rows] or None

    def get_menu_buttons(self, obj):
        rows = self.db.execute(
            select(MenuButton).where(MenuButton.menu_id == obj.id)
            .order_by(MenuButton.name.desc())  # 对齐 Meta.ordering=('-name',)
        ).scalars().all()
        return MenuButtonSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)


class WebRouterSerializer(CustomModelSerializer):
    """
    前端菜单路由的简单序列化器
    """

    model = Menu
    fields = ('id', 'parent', 'icon', 'sort', 'web_path', 'name', 'type', 'link_url',
              'component', 'component_name', 'cache', 'visible', 'status')
    read_only_fields = ["id"]


class MenuViewSet(CustomViewSet):
    """
    菜单管理接口
    list:查询
    create:新增
    update:修改
    retrieve:详情
    destroy:删除
    """
    model = Menu
    serializer_class = MenuSerializer
    create_serializer_class = MenuCreateSerializer
    update_serializer_class = MenuCreateSerializer
    filterset_fields = ['name', 'status', 'visible']
    search_fields = ['name', 'web_path']

    def update_sort(self):
        """菜单排序（上移、下移、拖拽）"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        menu_list = ast_convert(reqData.get("menus", []))
        if not menu_list:
            return ErrorResponse(msg="没有提供数据")
        menu_ids = [item['id'] for item in menu_list]
        if not menu_ids:
            return ErrorResponse(msg="参数错误")
        menus = self.db.execute(
            select(Menu).where(Menu.id.in_(menu_ids))
        ).scalars().all()
        menu_dict = {menu.id: menu for menu in menus}

        # 更新 sort / parent 字段
        updated_menus = []
        for item in menu_list:
            menu_id = item['id']
            sort_value = item['sort']
            parent_value = item['parent'] if item['parent'] else None
            if menu_id in menu_dict:
                menu_dict[menu_id].sort = sort_value
                menu_dict[menu_id].parent_id = parent_value
                updated_menus.append(menu_dict[menu_id])

        if not updated_menus:
            return ErrorResponse(msg="无此菜单")

        self.db.commit()
        return DetailResponse(msg="操作成功")

    def menu_tree(self):
        """用于菜单添加修改中获取父级菜单（对齐 Meta.ordering=('sort',)）"""
        queryset = self.db.execute(
            select(Menu).where(Menu.parent_id.is_(None))
            .order_by(Menu.sort.asc())
        ).scalars().all()
        serializer = MenuTreeSerializer(self.db, request=self.request, user=self.user)
        return SuccessResponse(data=serializer.serialize_many(queryset), msg="获取成功")

    def web_router(self):
        """用于前端获取当前角色的路由"""
        user = self.user
        if user.is_superuser:
            queryset = self.db.execute(
                select(Menu).where(Menu.status == True)  # noqa: E712
                .order_by(Menu.sort.asc())
            ).scalars().all()
        else:
            role_ids = get_user_role_ids(self.db, user.id)
            menu_ids = [r[0] for r in self.db.execute(
                select(RoleMenuPermission.menu_id).where(RoleMenuPermission.role_id.in_(role_ids))
            ).all()]
            # 对齐 self.filter_queryset(Menu.objects.filter(id__in=menuIds, status=True))
            query = select(Menu).where(Menu.id.in_(menu_ids), Menu.status == True)  # noqa: E712
            query = self.filter_queryset(query)
            queryset = self.db.execute(query).scalars().all()
        serializer = WebRouterSerializer(self.db, request=self.request, user=self.user)
        return DetailResponse(data=serializer.serialize_many(queryset), msg="获取成功")
