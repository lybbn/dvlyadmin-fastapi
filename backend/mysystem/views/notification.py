# -*- coding: utf-8 -*-

"""
@Remark: 消息通知
"""
import logging
from datetime import datetime

from sqlalchemy import or_, select, text

from mysystem.models import Notification, NotificationUsers, Users
from utils.common import get_parameter_dic, boolValue
from utils.jsonResponse import DetailResponse
from utils.serializers import CustomModelSerializer
from utils.pagination import paginate_queryset, paginate_response
from utils.viewset import CustomViewSet
from utils.ws import websocket_push

logger = logging.getLogger(__name__)


class NotificationFilterSet:
    """
    消息通知 过滤器
    """

    def __call__(self, db, request, query):
        params = request.query_params
        begin_at = params.get("beginAt", None)
        if begin_at:
            query = query.where(Notification.create_datetime >= begin_at)
        end_at = params.get("endAt", None)
        if end_at:
            query = query.where(Notification.create_datetime <= end_at)
        title = params.get("title", None)
        if title:
            query = query.where(Notification.title.ilike(f"%{title}%"))
        return query


class NotificationUsersFilterSet:
    """用户消息过滤器（search 联表 OR + is_read）"""

    def __call__(self, db, request, query):
        params = request.query_params
        # 对齐 filter_search：Q(notification__title__icontains) | Q(notification__content__icontains)
        search = params.get("search", None)
        if search:
            query = query.join(Notification, NotificationUsers.notification_id == Notification.id).where(
                or_(Notification.title.ilike(f"%{search}%"), Notification.content.ilike(f"%{search}%")))
        is_read = params.get("is_read", None)
        if is_read not in (None, ""):
            query = query.where(NotificationUsers.is_read == boolValue(is_read))
        return query


class NotificationSerializer(CustomModelSerializer):
    """
    消息通知-序列化器（users/dept/role 为 m2m → DRF 输出 id 列表）
    """

    model = Notification
    fields = "__all__"
    read_only_fields = ["id"]
    extra_output_fields = ["users", "dept", "role"]

    def get_users(self, obj):
        # through=NotificationUsers（lyadmin_message_users）
        rows = self.db.execute(
            select(NotificationUsers.user_id).where(NotificationUsers.notification_id == obj.id)
        ).all()
        return [r[0] for r in rows]

    def get_dept(self, obj):
        rows = self.db.execute(
            text("SELECT dept_id FROM lyadmin_message_dept WHERE notification_id = :nid"),
            {"nid": obj.id}).all()
        return [r[0] for r in rows]

    def get_role(self, obj):
        rows = self.db.execute(
            text("SELECT role_id FROM lyadmin_message_role WHERE notification_id = :nid"),
            {"nid": obj.id}).all()
        return [r[0] for r in rows]


class NotificationUsersSerializer(CustomModelSerializer):
    """
    消息通知 用户-序列化器
    """

    model = NotificationUsers
    fields = "__all__"
    read_only_fields = ["id"]


class NotificationListSerializer(CustomModelSerializer):
    """
    用户消息列表序列化器-序列化器
    """

    model = Notification
    fields = ("id", "target_type", "tag_type", "title", "content", "create_datetime")
    read_only_fields = ["id"]


class NotificationUsersListSerializer(CustomModelSerializer):
    """
    目标用户序列化器-序列化器（notification 嵌套完整对象）
    """

    model = NotificationUsers
    fields = "__all__"
    read_only_fields = ["id"]

    def get_notification(self, obj):
        # 对齐 notification = NotificationListSerializer()（FK 输出为嵌套对象）
        n = self.db.get(Notification, obj.notification_id)
        if n is None:
            return None
        return NotificationListSerializer(self.db, request=self.request, user=self.user).serialize(n)


class NotificationCreateUpdateSerializer(CustomModelSerializer):
    """
    消息通知 - 创建/编辑 序列化器（保存后同步 NotificationUsers 关联并推送通知）
    """

    model = Notification
    fields = "__all__"
    read_only_fields = ["id"]

    def run_validation(self, data):
        """暂存原始入参（target_type/users 等非模型字段在 save 阶段需要）"""
        self._initial_data = dict(data or {})
        return super().run_validation(data)

    def _sync_notification_users(self, instance):
        """对齐 NotificationCreateUpdateSerializer.save 中的关联同步与推送逻辑"""
        initial_data = self._initial_data
        target_type = initial_data.get('target_type')

        # 获取现有关联用户ID集合（如果是更新操作）
        existing_user_ids = set()
        if instance and instance.id:
            rows = self.db.execute(
                select(NotificationUsers.user_id).where(NotificationUsers.notification_id == instance.id)
            ).all()
            existing_user_ids = {r[0] for r in rows}

        # 根据目标类型确定目标用户
        if target_type in [0]:  # 平台公告
            users = [r[0] for r in self.db.execute(
                select(Users.id).where(Users.is_delete == False)  # noqa: E712
            ).all()]
        elif target_type in [1]:  # 按用户
            users = initial_data.get('users', [])
        else:
            users = []

        # 转换为集合便于操作
        new_user_ids = set(users)

        # 需要删除的关联（存在于现有但不在新列表中）
        to_delete_ids = existing_user_ids - new_user_ids
        if to_delete_ids:
            self.db.query(NotificationUsers).filter(
                NotificationUsers.notification_id == instance.id,
                NotificationUsers.user_id.in_(to_delete_ids)
            ).delete(synchronize_session=False)

        # 需要新增的关联（存在于新列表但不在现有中）
        to_create_ids = new_user_ids - existing_user_ids
        for user_id in to_create_ids:
            self.db.add(NotificationUsers(notification_id=instance.id, user_id=user_id))
        self.db.flush()

        # 发送WebSocket通知
        for user_id in new_user_ids:
            unread_nums = self.db.query(NotificationUsers).filter(
                NotificationUsers.user_id == user_id,
                NotificationUsers.is_read == False  # noqa: E712
            ).count()
            websocket_push(
                user_id,
                message={
                    "sender": 'system',
                    "msg_type": 'SYS',
                    "content": '您有一条新消息~',
                    "unread": unread_nums
                }
            )

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._sync_notification_users(instance)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._sync_notification_users(instance)
        return instance


class NotificationViewSet(CustomViewSet):
    """
    消息通知接口:
    """
    model = Notification
    serializer_class = NotificationSerializer
    filterset_class = NotificationFilterSet()
    create_serializer_class = NotificationCreateUpdateSerializer
    update_serializer_class = NotificationCreateUpdateSerializer
    search_fields = ('title',)

    def get_own_receive(self):
        """
        获取自己的接收消息
        """
        query = select(NotificationUsers).where(
            NotificationUsers.user_id == self.user.id,
            NotificationUsers.is_delete == False,  # noqa: E712
        ).order_by(NotificationUsers.id.desc())
        query = NotificationUsersFilterSet()(self.db, self.request, query)
        serializer = NotificationUsersListSerializer(self.db, request=self.request, user=self.user)
        items, total, page, limit = paginate_queryset(self.db, self.request, query)
        data = serializer.serialize_many(items)
        return paginate_response(self.request, data, total, page, limit)

    def del_own_receive(self):
        """
        删除自己的接收消息
        """
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id")
        self.db.query(NotificationUsers).filter(
            NotificationUsers.id == id, NotificationUsers.user_id == self.user.id
        ).update({"is_delete": True}, synchronize_session=False)
        self.db.commit()
        return DetailResponse(msg="删除成功")

    def read_own_receive(self):
        """
        设置自己的接收消息已读
        """
        reqData = get_parameter_dic(self.request, self.get_request_data())
        id = reqData.get("id")
        type = reqData.get("type", "")
        if not type:
            self.db.query(NotificationUsers).filter(
                NotificationUsers.id == id, NotificationUsers.user_id == self.user.id,
                NotificationUsers.is_read == False  # noqa: E712
            ).update({"is_read": True, "read_at": datetime.now()}, synchronize_session=False)
        elif type == "ALL":
            self.db.query(NotificationUsers).filter(
                NotificationUsers.user_id == self.user.id,
                NotificationUsers.is_read == False  # noqa: E712
            ).update({"is_read": True, "read_at": datetime.now()}, synchronize_session=False)
        self.db.commit()
        return DetailResponse(msg="设置成功")
