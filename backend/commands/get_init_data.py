# -*- coding: utf-8 -*-
"""
@Remark: 获取初始化数据命令（对应 Django 版: python manage.py get_init_data your_app.models_name）
用法: python run.py get_init_data mysystem.Dept [--fields a,b] [--exclude a,b] [--order_by id]
说明：输出格式与 Django 版一致（表头 + 每行 str(dict) + ','），可直接粘贴回 initialize.py
"""
from sqlalchemy import select

from application.database import SessionLocal
from commands.base import err, ok

# 默认排除字段（对齐 Django 版 get_init_data 的 EXCLUDE_FIELDS）
EXCLUDE_FIELDS = ["create_datetime", "update_datetime", "is_delete", "modifier", "dept_belong"]


def add_arguments(parser):
    parser.add_argument("model_name", type=str, help="模型名称（格式：mysystem.ModelName，兼容裸类名）")
    parser.add_argument("--fields", type=str, help="指定要获取的字段（逗号分隔），默认取全部字段（除排除字段外）")
    parser.add_argument("--exclude", type=str, help="要排除的字段（逗号分隔），覆盖默认排除字段")
    parser.add_argument("--order_by", type=str, default="id", help="排序字段（默认：id）")


def _resolve_model(model_name):
    """解析模型：'mysystem.Dept' → mysystem.models.Dept（兼容裸类名）"""
    import mysystem.models as models_module

    class_name = model_name.rsplit(".", 1)[-1]
    model = getattr(models_module, class_name, None)
    if model is None or not hasattr(model, "__tablename__"):
        raise LookupError(f"找不到模型: {model_name}")
    return model


def handle(args):
    fields = [f.strip() for f in args.fields.split(",") if f.strip()] if args.fields else None
    exclude_fields = [f.strip() for f in args.exclude.split(",")] if args.exclude else EXCLUDE_FIELDS
    order_by = args.order_by

    try:
        model = _resolve_model(args.model_name)
    except LookupError as e:
        err(str(e))
        return 0

    if fields is None:
        fields = [col.name for col in model.__table__.columns if col.name not in exclude_fields]

    try:
        order_attr = getattr(model, order_by)
    except AttributeError:
        err(f"发生错误: 排序字段 {order_by} 不存在")
        return 0

    db = SessionLocal()
    try:
        rows = db.execute(select(model).order_by(order_attr)).scalars().all()

        result = []
        for obj in rows:
            item = {}
            for field in fields:
                try:
                    item[field] = getattr(obj, field)
                except Exception as e:
                    item[field] = f"ERROR: {str(e)}"
            result.append(item)

        ok(f"\n{args.model_name} 数据（共 {len(result)} 条）：")
        for item in result:
            ok(str(item) + ",")
    except Exception as e:
        err(f"发生错误: {str(e)}")
    finally:
        db.close()
    return 0