# -*- coding: utf-8 -*-

"""
@Remark: 角色管理
"""
from sqlalchemy import select

from mysystem.models import Role, Menu, MenuButton, MenuField, RoleMenuPermission, RoleMenuButtonPermission, FieldPermission
from mysystem.views.menu import MenuSerializer
from mysystem.views.menu_field import MenuFieldSerializer
from mysystem.views.menu_button import MenuButtonSerializer
from utils.common import get_parameter_dic, ast_convert
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet


class RoleFilterSet:
    """
    角色管理 过滤器
    beginAt/endAt → create_datetime 区间，name 模糊，status 精确
    """

    def __call__(self, db, request, query):
        params = request.query_params
        begin_at = params.get("beginAt", None)
        if begin_at:
            query = query.where(Role.create_datetime >= begin_at)
        end_at = params.get("endAt", None)
        if end_at:
            query = query.where(Role.create_datetime <= end_at)
        name = params.get("name", None)
        if name:
            query = query.where(Role.name.ilike(f"%{name}%"))
        status = params.get("status", None)
        if status not in (None, ""):
            from utils.common import boolValue
            query = query.where(Role.status == boolValue(status))
        return query


class RoleSerializer(CustomModelSerializer):
    """
    角色-序列化器
    """

    model = Role
    fields = "__all__"
    read_only_fields = ["id"]


class RoleMenuPermissionSerializer(CustomModelSerializer):
    """
    角色菜单权限-序列化器
    """

    model = RoleMenuPermission
    fields = "__all__"
    read_only_fields = ["id"]


class RoleMenuButtonPermissionSerializer(CustomModelSerializer):
    """
    角色菜单按钮权限-序列化器
    """

    model = RoleMenuButtonPermission
    fields = "__all__"
    read_only_fields = ["id"]


class FieldPermissionSerializer(CustomModelSerializer):
    """
    角色菜单列权限-序列化器（field_name 由 field_id 关联 MenuField 取得）
    """

    model = FieldPermission
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["field_name"]

    def get_field_name(self, obj):
        # 对齐 obj.field.field_name（Django related_name='menu_field_permission'）
        mf = self.db.get(MenuField, obj.field_id)
        return mf.field_name if mf else None


class RoleCreateUpdateSerializer(CustomModelSerializer):
    """
    角色管理 创建/更新时的序列化器（对齐 UniqueValidator：key/name 必须唯一）
    """

    model = Role
    fields = "__all__"
    read_only_fields = ["id"]

    def validate(self, data):
        # 对齐 DRF UniqueValidator（Role 模型 error_messages）+ viewset.update 挂载的 instance 排除自身
        current = getattr(self, "instance", None)
        current_id = current.id if current is not None else (data.get("id") or "")
        key = data.get("key")
        if key:
            exists = self.db.query(Role.id).filter(Role.key == key, Role.id != current_id).first()
            if exists:
                from utils.exception import APIException, drf_validation_msg
                raise APIException(code=4000, message=drf_validation_msg("key", "权限字符已存在"))
        name = data.get("name")
        if name:
            exists = self.db.query(Role.id).filter(Role.name == name, Role.id != current_id).first()
            if exists:
                from utils.exception import APIException, drf_validation_msg
                raise APIException(code=4000, message=drf_validation_msg("name", "角色名称已存在"))
        return data


class MenuPermissonSerializer(CustomModelSerializer):
    """
    菜单的按钮权限（menu_buttons/menu_fields 嵌套输出）
    """

    model = Menu
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["menu_buttons", "menu_fields"]

    def get_menu_buttons(self, obj):
        rows = self.db.execute(
            select(MenuButton).where(MenuButton.menu_id == obj.id)
            .order_by(MenuButton.name.desc())  # 对齐 Meta.ordering=('-name',)
        ).scalars().all()
        return MenuButtonSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)

    def get_menu_fields(self, obj):
        rows = self.db.execute(
            select(MenuField).where(MenuField.menu_id == obj.id)
            .order_by(MenuField.id.asc())  # 对齐 Meta.ordering=("id",)
        ).scalars().all()
        return MenuFieldSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)


class RoleViewSet(CustomViewSet):
    """
    角色管理接口
    list:查询
    create:新增
    update:修改
    retrieve:单例
    destroy:删除
    """
    model = Role
    serializer_class = RoleSerializer
    create_serializer_class = RoleCreateUpdateSerializer
    update_serializer_class = RoleCreateUpdateSerializer
    filterset_class = RoleFilterSet()
    search_fields = ('name', 'key')

    def get_queryset(self):
        # 对齐 Django queryset = Role.objects.all().order_by("id")（order_by 覆盖 Meta.ordering）
        return super().get_queryset().order_by(None).order_by(Role.id.asc())

    def set_status(self):
        """禁用/启用"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id", "")
        query = self.filter_queryset(self.get_queryset()).where(Role.id == id)
        instance = self.db.execute(query).scalars().first()
        if instance:
            instance.status = False if instance.status else True
            self.db.commit()
            return DetailResponse(data=None, msg="设置成功")
        else:
            return ErrorResponse(msg="未获取到数据")

    def roleId_to_menu(self):
        """通过角色id获取该角色用于的菜单（对齐 Django 版：返回全部启用菜单及按钮/列）"""
        queryset = self.db.execute(
            select(Menu).where(Menu.status == True)  # noqa: E712
            .order_by(Menu.sort.asc())
        ).scalars().all()
        serializer = MenuPermissonSerializer(self.db, request=self.request, user=self.user)
        return DetailResponse(data=serializer.serialize_many(queryset))


class RolePermissonSerializer(CustomModelSerializer):
    """
    菜单的按钮权限（角色关联的菜单/按钮/列权限嵌套输出）
    """

    model = Role
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["role_menu_permission", "role_button_permission", "role_field_permission"]

    def get_role_menu_permission(self, obj):
        rows = self.db.execute(
            select(RoleMenuPermission).where(RoleMenuPermission.role_id == obj.id)
        ).scalars().all()
        return RoleMenuPermissionSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)

    def get_role_button_permission(self, obj):
        rows = self.db.execute(
            select(RoleMenuButtonPermission).where(RoleMenuButtonPermission.role_id == obj.id)
        ).scalars().all()
        return RoleMenuButtonPermissionSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)

    def get_role_field_permission(self, obj):
        rows = self.db.execute(
            select(FieldPermission).where(FieldPermission.role_id == obj.id)
        ).scalars().all()
        return FieldPermissionSerializer(self.db, request=self.request, user=self.user).serialize_many(rows)


class RolePermissionViewSet(CustomViewSet):
    """
    角色权限管理接口
    list:查询
    create:新增
    update:修改
    retrieve:单例
    destroy:删除
    """
    model = Role
    serializer_class = RolePermissonSerializer
    filterset_class = RoleFilterSet()
    search_fields = ('name', 'key')

    def get_queryset(self):
        # 对齐 Role.objects.filter(status=True).order_by("id")（order_by 覆盖 Meta.ordering）
        return (super().get_queryset()
                .where(Role.status == True)  # noqa: E712
                .order_by(None).order_by(Role.id.asc()))

    def save_permission(self):
        """保存权限"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        role_id = reqData.get("role_id", "")
        query = self.filter_queryset(self.get_queryset()).where(Role.id == role_id)
        instance = self.db.execute(query).scalars().first()
        if instance:
            RoleMenuPermission_list = ast_convert(reqData.get("RoleMenuPermission", []))
            RoleMenuButtonPermission_list = ast_convert(reqData.get("RoleMenuButtonPermission", []))
            FieldPermission_list = ast_convert(reqData.get("FieldPermission", []))

            try:
                # 1. 删除旧权限
                self._delete_old_permissions(role_id)

                # 2. 批量创建新权限
                stats = {
                    'menu': self._bulk_create_menu_permissions(RoleMenuPermission_list),
                    'button': self._bulk_create_button_permissions(RoleMenuButtonPermission_list),
                    'field': self._bulk_create_field_permissions(FieldPermission_list)
                }
                self.db.commit()
                return DetailResponse(data=stats, msg="保存成功")

            except Exception as e:
                self.db.rollback()
                from utils.exception import APIException
                if isinstance(e, APIException):
                    raise
                raise APIException(message=f"服务器错误:{str(e)}")

        else:
            return ErrorResponse(msg="未获取到数据")

    def _delete_old_permissions(self, role_id):
        """删除角色所有旧权限"""
        self.db.query(RoleMenuPermission).filter(RoleMenuPermission.role_id == role_id).delete()
        self.db.query(RoleMenuButtonPermission).filter(RoleMenuButtonPermission.role_id == role_id).delete()
        self.db.query(FieldPermission).filter(FieldPermission.role_id == role_id).delete()

    def _bulk_create_menu_permissions(self, data):
        """批量创建菜单权限"""
        if not data:
            return 0
        serializer = RoleMenuPermissionSerializer(self.db, request=self.request, user=self.user)
        for item in data:
            validated = serializer.run_validation(item)
            serializer.create(validated)
        return len(data)

    def _bulk_create_button_permissions(self, data):
        """批量创建按钮权限"""
        if not data:
            return 0
        serializer = RoleMenuButtonPermissionSerializer(self.db, request=self.request, user=self.user)
        for item in data:
            validated = serializer.run_validation(item)
            serializer.create(validated)
        return len(data)

    def _bulk_create_field_permissions(self, data):
        """批量创建字段权限"""
        if not data:
            return 0
        serializer = FieldPermissionSerializer(self.db, request=self.request, user=self.user)
        for item in data:
            validated = serializer.run_validation(item)
            serializer.create(validated)
        return len(data)
