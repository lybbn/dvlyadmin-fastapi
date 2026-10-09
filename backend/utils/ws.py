# -*- coding: utf-8 -*-
"""
@Remark: WebSocket 消息推送（对应 Django channels wsmessage.py + wsrouting.py + JwtAuthMiddleware）
与 Django 版行为对齐的关键点：
(1) 子协议认证：Sec-WebSocket-Protocol 头须为 "JWTLYADMIN, JWTlybbn<token>" 精确两段
    （前端 websocket.js：'JWTlybbn' + token 无空格拼接；JwtAuthMiddleware：split(b', ')
    → alltoken[0]==b'JWTLYADMIN' → parts=split(b'lybbn') → parts[0]==b'JWT'）
(2) 认证失败/用户不存在/未激活 → 连接直接拒绝（Django return None → 403）
(3) 权限：/ws/msg/ + WS 方法 → 恒 True（对齐 has_permission 的 method==5 and api=="/ws/msg/" 短路）
(4) accept 时回传子协议 "JWTLYADMIN"；连接成功推送欢迎消息或未读数
(5) 房间分组 "notifications_user_<user_id>"（对齐 channel_layer group_add/discard/group_send）
(6) receive 恒忽略（对齐 Django receive: pass）
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from application import settings
from application.database import SessionLocal
from mysystem.models import NotificationUsers, Users
from utils.security import TokenError

logger = logging.getLogger(__name__)

ws_router = APIRouter()


def set_message(sender, msg_type, msg, unread=0):
    text = {
        'sender': sender,
        'msg_type': msg_type,
        'content': msg,
        'unread': unread
    }
    return text


class ConnectionManager:
    """
    连接管理（对齐 channels InMemoryChannelLayer 的 group_add/group_discard/group_send；
    单进程内存版，跨进程部署需换 redis layer——与 Django InMemory layer 限制一致）
    """
    def __init__(self):
        # {user_id: [websocket, ...]}（同用户可开多个标签页 → 多连接）
        self._groups: dict = {}
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop):
        """lifespan 启动时保存主事件循环（同步线程池线程推送时需要跨线程调度）"""
        self.main_loop = loop

    async def connect(self, user_id, websocket: WebSocket):
        await websocket.accept(subprotocol="JWTLYADMIN")
        self._groups.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id, websocket: WebSocket):
        conns = self._groups.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if user_id in self._groups and not self._groups[user_id]:
            self._groups.pop(user_id, None)

    def _dispatch_sync(self, user_id, message: dict):
        """同步上下文入口（websocket_push 被 DRF 风格同步视图调用）→ 调度回主事件循环"""
        if self.main_loop is None or self.main_loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.group_send(user_id, message), self.main_loop)

    async def group_send(self, user_id, message: dict):
        """对齐 channel_layer.group_send(room_group_name, {"type": "push.message", "json": message})"""
        dead = []
        for ws in self._groups.get(user_id, []):
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


manager = ConnectionManager()


def websocket_push(user_id, message):
    """
    主动推送消息（对应 Django notification.websocket_push 的 async_to_sync(group_send)）
    """
    manager._dispatch_sync(user_id, message)


def _get_message_unread_count(user_id) -> int:
    """获取用户的未读消息数量（对齐 wsmessage._get_message_unread_count）"""
    from sqlalchemy import func, select
    db = SessionLocal()
    try:
        count = db.execute(
            select(func.count(NotificationUsers.id))
            .where(NotificationUsers.user_id == user_id, NotificationUsers.is_read == False)
        ).scalar()
        return count or 0
    finally:
        db.close()


def _authenticate_ws(subprotocol_header: str):
    """
    WebSocket 认证（对齐 JwtAuthMiddleware.__call__）
    :return: (user 或 None, 拒绝原因)
    """
    protocol = subprotocol_header
    if len(protocol) == 0:
        return None, "Empty AUTHORIZATION header sent"
    alltoken = protocol.split(', ')
    if not len(alltoken) == 2:
        return None, "协议格式错误"
    if not alltoken[0] == 'JWTLYADMIN':
        return None, "协议前缀错误"
    parts = alltoken[1].split('lybbn')
    if len(parts) == 0:
        return None, "token格式错误"
    if parts[0] not in ('JWT', 'jwt'):
        return None, "认证类型错误"
    if len(parts) != 2:
        return None, "token格式错误"
    token = parts[1]
    try:
        # 对齐 UntypedToken(token)：只验签/过期/jti，不校验 token_type
        import jwt as pyjwt
        decoded = pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if "jti" not in decoded:
            raise TokenError("Token has no id")
    except TokenError:
        return None, "token无效"
    except Exception:
        return None, "token无效"
    db = SessionLocal()
    try:
        user = db.get(Users, decoded.get("user_id"))
        if user is None:
            return None, "用户不存在"
        if not user.is_active:
            return None, "用户未激活"
        # 对齐 has_permission：method=5(WS) 且 api=="/ws/msg/" → True（短路，任何有效用户可连）
        return user, None
    finally:
        db.close()


@ws_router.websocket("/ws/msg/")
async def ws_msg(websocket: WebSocket):
    """消息通知 WebSocket（对应 NotificationConsumer）"""
    protocol_header = websocket.headers.get("sec-websocket-protocol", "")
    user, reason = _authenticate_ws(protocol_header)
    if user is None:
        # 对齐 JwtAuthMiddleware return None → 连接拒绝（403）
        await websocket.close(code=1008, reason=reason or "unauthorized")
        return

    user_id = user.id
    room_group_name = f'notifications_user_{user_id}'
    await manager.connect(user_id, websocket)

    try:
        unread_count = _get_message_unread_count(user_id)
        if unread_count == 0:
            await websocket.send_text(json.dumps(
                set_message('system', 'SYS', f'{user.name}，你好！消息通知已上线！'),
                ensure_ascii=False))
        else:
            await websocket.send_text(json.dumps(
                set_message('system', 'SYS', "请查看您的未读消息~", unread=unread_count),
                ensure_ascii=False))
        # receive: pass（对齐 Django，收到的任何消息都忽略，仅保持连接）
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws 连接异常")
    finally:
        manager.disconnect(user_id, websocket)
        # 对齐 disconnect: group_discard + close（close 由框架完成）
