# -*- coding: utf-8 -*-

"""
@Remark: 系统管理的路由文件（对应 Django mysystem/urls.py）
注册顺序与 Django 版一致：自定义 action 手工路由先于 ViewSet router 注册，
保证 /dept/set_status/ 等先于 /dept/{pk}/ 匹配。
说明：GetDictionaryInfoView/GetDictionaryAllView 在 Django 中定义但未注册路由（死代码），此处同样不注册。
"""

from fastapi import APIRouter

from mysystem.views.button import ButtonViewSet
from mysystem.views.dept import DeptViewSet
from mysystem.views.menu import MenuViewSet
from mysystem.views.menu_button import MenuButtonViewSet
from mysystem.views.menu_field import MenuFieldViewSet
from mysystem.views.operation_log import OperationLogViewSet
from mysystem.views.role import RoleViewSet, RolePermissionViewSet
from mysystem.views.user import UserViewSet
from mysystem.views.dictionary import DictionaryViewSet
from mysystem.views.login_log import LoginLogViewSet
from mysystem.views.system_config import SystemConfigViewSet
from mysystem.views.notification import NotificationViewSet
from mysystem.views.frontend import frontend_router

# 各视图集共用的路由容器（对应 system_url = routers.SimpleRouter()）
system_router = APIRouter()

# sys_image_upload 对齐 Django urlpatterns 首位手工注册（/api/system/sys_image_upload/）
system_router.include_router(frontend_router)

# ---------- 自定义 action（对齐 re_path 手工注册，必须先于 CRUD 路由） ----------
MenuViewSet.register_action(system_router, 'menu/update_sort/', ['post'], 'update_sort')
MenuViewSet.register_action(system_router, 'menu_tree/', ['get'], 'menu_tree')
MenuButtonViewSet.register_action(system_router, 'menu_button/menu_button_permission/', ['get'], 'menu_button_permission')
MenuButtonViewSet.register_action(system_router, 'menu_button/batch_generate/', ['post'], 'batch_generate')
MenuFieldViewSet.register_action(system_router, 'menu_field/get_models/', ['get'], 'get_models')
MenuFieldViewSet.register_action(system_router, 'menu_field/auto_create/', ['post'], 'auto_create')
MenuViewSet.register_action(system_router, 'menu/web_router/', ['get'], 'web_router')

DeptViewSet.register_action(system_router, 'dept/set_status/', ['post'], 'set_status')
RoleViewSet.register_action(system_router, 'role/set_status/', ['post'], 'set_status')
UserViewSet.register_action(system_router, 'user/set_status/', ['post'], 'set_status')
DictionaryViewSet.register_action(system_router, 'dictionary/set_status/', ['post'], 'set_status')

UserViewSet.register_action(system_router, 'user/reset_password/{pk}/', ['put'], 'reset_password')

# 对齐 re_path('role_id_to_menu/(?P<pk>.*?)/', ...)（Django 版实现未使用 pk，返回全部菜单）
RoleViewSet.register_action(system_router, 'role_id_to_menu/{pk}/', ['get'], 'roleId_to_menu')
RolePermissionViewSet.register_action(system_router, 'role_permission/save_permission/', ['post'], 'save_permission')

OperationLogViewSet.register_action(system_router, 'operation_log/deletealllogs/', ['delete'], 'deletealllogs')
OperationLogViewSet.register_action(system_router, 'operation_log/getOwnerLogs/', ['get'], 'getOwnerLogs')

LoginLogViewSet.register_action(system_router, 'login_log/deletealllogs/', ['delete'], 'deletealllogs')
LoginLogViewSet.register_action(system_router, 'login_log/getOwnerLogs/', ['get'], 'getOwnerLogs')

# user_info/change_password/change_avatar 已在阶段1 user_router 注册（/api/system/user/...），此处不重复
SystemConfigViewSet.register_action(system_router, 'sysconfig/save_content/{pk}/', ['put'], 'save_content')
SystemConfigViewSet.register_action(system_router, 'sysconfig/get_models_info_list/', ['get'], 'get_models_info_list')

NotificationViewSet.register_action(system_router, 'msg/ownmsg/', ['get'], 'get_own_receive')
NotificationViewSet.register_action(system_router, 'msg/delownmsg/', ['post'], 'del_own_receive')
NotificationViewSet.register_action(system_router, 'msg/readownmsg/', ['post'], 'read_own_receive')

# ---------- ViewSet CRUD（对齐 system_url.register） ----------
MenuViewSet.register(system_router, prefix='menu')
ButtonViewSet.register(system_router, prefix='button')
MenuButtonViewSet.register(system_router, prefix='menu_button')
MenuFieldViewSet.register(system_router, prefix='menu_field')
RoleViewSet.register(system_router, prefix='role')
RolePermissionViewSet.register(system_router, prefix='role_permission')
DeptViewSet.register(system_router, prefix='dept')
UserViewSet.register(system_router, prefix='user')
OperationLogViewSet.register(system_router, prefix='operation_log')
DictionaryViewSet.register(system_router, prefix='dictionary')
LoginLogViewSet.register(system_router, prefix='login_log')
SystemConfigViewSet.register(system_router, prefix='sysconfig')
NotificationViewSet.register(system_router, prefix='msg')
