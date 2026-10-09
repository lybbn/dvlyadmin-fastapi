# -*- coding: utf-8 -*-
"""
@Remark: 用户视图（对应 Django mysystem/views/user.py 的 UserViewSet）
阶段1：user_info/update_user_info/change_password/change_avatar（个人中心链路）
阶段3：UserViewSet CRUD（用户管理列表/新增/编辑/删除/导入导出）+ set_status/reset_password
"""
import re

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.database import get_db
from mysystem.models import Role, Users, UsersRole, get_user_roles
from utils.common import formatdatetime, is_valid_email
from utils.exception import APIException
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.permission import get_current_user
from utils.security import check_password, make_password
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet

user_router = APIRouter()


def _get_role_info(db: Session, user: Users):
    """对齐 Django role.values('id', 'name', 'key') 的返回结构"""
    roles = get_user_roles(db, user.id)
    return [{"id": r.id, "name": r.name, "key": r.key} for r in roles]


@user_router.get("/user_info/")
def user_info(request: Request, db: Session = Depends(get_db),
              user: Users = Depends(get_current_user)):
    """获取当前用户信息"""
    if user.identity not in [0, 1]:
        return ErrorResponse(msg="用户类型错误")
    department = ""
    dept_id = user.dept_id
    if dept_id:
        # 对齐 user.dept.name（FK 无约束，按主键查询部门名）
        from mysystem.models import Dept
        dept = db.get(Dept, dept_id)
        if dept:
            department = dept.name
    result = {
        "id": user.id,
        "avatar": user.avatar,
        "nickname": user.nickname,
        "name": user.name,
        "mobile": user.mobile,
        "gender": user.gender,
        "email": user.email,
        "dept_id": dept_id,
        "department": department,
        "is_superuser": user.is_superuser,
        "identity": user.identity,
        "create_datetime": formatdatetime(user.create_datetime),
        "last_login": formatdatetime(user.last_login),
    }
    result['role_info'] = _get_role_info(db, user)
    if user.is_superuser:
        result['role_info'] = [{"id": "", "name": "超级管理员", "key": ""}]
        result['department'] = "超级管理员"
    return DetailResponse(data=result, msg="获取成功")


@user_router.put("/user_info/")
def update_user_info(request: Request, db: Session = Depends(get_db),
                     user: Users = Depends(get_current_user), body: dict = Body(default={})):
    """修改当前用户信息"""
    if user.identity not in [0, 1]:
        return ErrorResponse(msg="用户类型错误")
    email = body.get('email')
    name = body.get('name')
    gender = body.get('gender')
    mobile = body.get('mobile')
    nickname = body.get('nickname')
    if gender not in [0, 1, 2]:
        return ErrorResponse(msg="性别参数错误")
    if not all([name, nickname, mobile]):
        return ErrorResponse(msg="姓名、昵称、电话不能为空")
    if not is_valid_email(email):
        return ErrorResponse(msg="邮箱格式错误")
    new_data = {"email": email, "name": name, "gender": gender, "mobile": mobile, "nickname": nickname}
    for k, v in new_data.items():
        setattr(user, k, v)
    db.commit()
    return DetailResponse(data=None, msg="修改成功")


@user_router.post("/change_password/")
def change_password(request: Request, db: Session = Depends(get_db),
                    user: Users = Depends(get_current_user), body: dict = Body(default={})):
    """密码修改"""
    if user.identity not in [0, 1]:
        return ErrorResponse(msg="用户类型错误")
    instance = db.execute(
        select(Users).where(Users.id == user.id, Users.identity.in_([0, 1]))
    ).scalars().first()
    old_pwd = body.get('currentPassword')
    new_pwd = body.get('newPassword')
    new_pwd2 = body.get('confirmPassword')
    if instance:
        if new_pwd != new_pwd2:
            return ErrorResponse(msg="2次密码不匹配")
        import re
        if not re.match(r'^(?=.*[0-9])(?=.*[a-zA-Z]).{6,20}$', new_pwd or ""):
            return ErrorResponse(msg="密码必须包含字母和数字，且长度为6-20个字符")
        if check_password(old_pwd or "", instance.password):
            instance.password = make_password(new_pwd)
            db.commit()
            return DetailResponse(data=None, msg="修改成功")
        else:
            return ErrorResponse(msg="旧密码不正确")
    else:
        return ErrorResponse(msg="未获取到用户")


@user_router.post("/change_avatar/")
def change_avatar(request: Request, db: Session = Depends(get_db),
                  user: Users = Depends(get_current_user), body: dict = Body(default={})):
    """头像修改"""
    if user.identity not in [0, 1]:
        return ErrorResponse(msg="用户类型错误")
    instance = db.execute(
        select(Users).where(Users.id == user.id, Users.identity.in_([0, 1]))
    ).scalars().first()
    avatar = body.get('avatar')
    if instance:
        if not avatar:
            return ErrorResponse(msg="请上传头像")
        instance.avatar = avatar
        db.commit()
        return DetailResponse(data=None, msg="修改成功")
    else:
        return ErrorResponse(msg="未获取到用户")


# ================================================= #
# ************** UserViewSet（阶段3 用户管理 CRUD） ************** #
# ================================================= #

class UsersManageTimeFilter:
    """
    用户管理 简单过滤器
    """

    def __call__(self, db, request, query):
        params = request.query_params
        begin_at = params.get("beginAt", None)
        if begin_at:
            query = query.where(Users.create_datetime >= begin_at)
        end_at = params.get("endAt", None)
        if end_at:
            query = query.where(Users.create_datetime <= end_at)
        for field in ("username", "nickname", "name", "mobile"):
            v = params.get(field, None)
            if v:
                query = query.where(getattr(Users, field).ilike(f"%{v}%"))
        v = params.get("is_active", None)
        if v not in (None, ""):
            from utils.common import boolValue
            query = query.where(Users.is_active == boolValue(v))
        v = params.get("dept_id", None)
        if v not in (None, ""):
            query = query.where(Users.dept_id == v)
        return query


class UserSerializer(CustomModelSerializer):
    """
    用户管理-序列化器（排除 password；roleNames/deptName 计算字段；role 多对多输出 id 列表）
    """
    model = Users
    fields = "__all__"
    exclude = ['password']
    read_only_fields = ["id"]
    m2m = {"role": (UsersRole, "users_id", "role_id")}
    extra_output_fields = ["roleNames", "deptName"]

    def get_deptName(self, obj):
        try:
            if not obj.dept_id:
                return ""
            from mysystem.models import Dept
            dept = self.db.get(Dept, obj.dept_id)
            return dept.name if dept else ""
        except Exception:
            return ""

    def get_roleNames(self, obj):
        rows = self.db.execute(
            select(Role.name).join(UsersRole, UsersRole.role_id == Role.id)
            .where(UsersRole.users_id == obj.id)
        ).all()
        return [r[0] for r in rows]


class UserImportSerializer(CustomModelSerializer):
    """
    用户管理导入-序列化器
    """
    model = Users
    fields = "__all__"
    read_only_fields = ["id"]
    m2m = {"role": (UsersRole, "users_id", "role_id")}

    def validate(self, data):
        if data.get("username"):
            exists = self.db.query(Users.id).filter(Users.username == data["username"]).first()
            if exists:
                raise APIException(message="账号必须唯一")
        # 对齐 password default=make_password("123456") 与 create 处理
        if data.get("password"):
            data['password'] = make_password(data['password'])
        else:
            data['password'] = make_password("123456")
        data['identity'] = 1
        if data.get('name'):
            data['nickname'] = data['name']
        return data


class UserCreateSerializer(CustomModelSerializer):
    """
    管理员用户新增-序列化器
    """
    model = Users
    fields = "__all__"
    read_only_fields = ["id"]
    m2m = {"role": (UsersRole, "users_id", "role_id")}

    def validate(self, data):
        if data.get("username"):
            exists = self.db.query(Users.id).filter(Users.username == data["username"]).first()
            if exists:
                raise APIException(message="账号必须唯一")
        if data.get("password"):
            data['password'] = make_password(data['password'])
        else:
            data['password'] = make_password("123456")
        data['identity'] = 1
        if data.get('name'):
            data['nickname'] = data['name']
        return data


class UserUpdateSerializer(CustomModelSerializer):
    """
    用户修改-序列化器
    """
    model = Users
    fields = "__all__"
    read_only_fields = ["id"]
    m2m = {"role": (UsersRole, "users_id", "role_id")}

    def validate(self, data):
        if data.get("username"):
            ins_id = (data.get("id") or "")
            exists = self.db.query(Users.id).filter(
                Users.username == data["username"], Users.id != ins_id).first()
            if exists:
                raise APIException(message="账号必须唯一")
        if data.get("password"):
            data['password'] = make_password(data['password'])
        else:
            data.pop("password", None)
        if data.get('name'):
            data['nickname'] = data['name']
        return data


class UserViewSet(CustomViewSet):
    """
    后台管理员用户接口:
    """
    model = Users
    serializer_class = UserSerializer
    create_serializer_class = UserCreateSerializer
    update_serializer_class = UserUpdateSerializer
    filterset_class = UsersManageTimeFilter()
    import_field_dict = {
        "ID": "id",
        "账号": {'field': 'username', 'example': 'test'},
        "姓名": {'field': 'name', 'example': 'lybbn'},
        "头像": {'field': 'avatar', 'example': "URL地址"},
        "电话": "mobile",
        "邮箱": "email",
        "密码": {'field': 'password', 'example': "123456"},
        "部门": {'field': 'dept', 'example': "部门ID"},
        "角色": {'field': 'role', 'example': "角色ID（可为空，如有多个用逗号分隔）", 'many': True, 'separator': ','},
        "状态": {'field': 'is_active', 'example': 1},
    }
    import_serializer_class = UserImportSerializer

    def get_queryset(self):
        # 对齐 Users.objects.filter(identity=1, is_delete=False).order_by('-create_datetime')
        return (super().get_queryset()
                .where(Users.identity == 1, Users.is_delete == False))  # noqa: E712

    def set_status(self):
        """禁用/启用"""
        from utils.common import get_parameter_dic
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id", "")
        query = self.filter_queryset(self.get_queryset()).where(Users.id == id)
        instance = self.db.execute(query).scalars().first()
        if instance:
            instance.is_active = False if instance.is_active else True
            self.db.commit()
            return DetailResponse(data=None, msg="设置成功")
        else:
            return ErrorResponse(msg="未获取到数据")

    def reset_password(self):
        """重置用户密码（仅超管；pk 从路径取）"""
        if not self.user.is_superuser:
            return ErrorResponse(msg="只允许超级管理员进行密码重置操作")
        pk = self.request.path_params.get("pk")
        user = self.db.get(Users, pk)
        if user is None:
            return ErrorResponse(msg="指定用户不存在")
        try:
            data = self.get_request_data()
            new_pwd = data.get('newPassword')
            user.password = make_password(new_pwd)
            self.db.commit()
            return DetailResponse(msg="设置成功")
        except Exception as e:
            self.db.rollback()
            return ErrorResponse(msg=f"密码重置错误：{str(e)}")
