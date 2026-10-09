# -*- coding: utf-8 -*-

"""
@Remark: 菜单列管理
"""
from mysystem.models import MenuField, Menu
from utils.common import get_parameter_dic
from utils.jsonResponse import DetailResponse, ErrorResponse
from utils.models import get_project_app_models
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomViewSet


class MenuFieldSerializer(CustomModelSerializer):
    """
    菜单列-序列化器
    """

    model = MenuField
    fields = "__all__"
    read_only_fields = ["id"]


class MenuFieldViewSet(CustomViewSet):
    """
    菜单列接口:
    """
    model = MenuField
    serializer_class = MenuFieldSerializer
    filterset_fields = ['menu']

    def get_models(self):
        """获取所有自定义项目app下的model"""
        data = []
        for model in get_project_app_models(include_fields=False):
            data.append({
                'app': model['app'],
                'title': model['verbose'],
                'model': model['model']
            })
        return DetailResponse(data=data)

    def auto_create(self):
        """自动批量生成列"""
        reqData = get_parameter_dic(self.request, self.get_request_data())
        menu_id = reqData.get("menu", "")
        model_name = reqData.get("model", "")  # 若不提供指定model，则默认为自动发现该菜单模型名
        if not menu_id:
            return ErrorResponse(msg="请提供要添加的菜单")
        if not model_name:
            return ErrorResponse(msg="请提供所属模型名")
        ins = self.db.get(Menu, menu_id)
        if not ins:
            return ErrorResponse(msg="无此菜单")
        serializer = self.get_serializer(MenuFieldSerializer)
        for model in get_project_app_models():
            if model['model'] == model_name:
                for field in model['fields']:
                    exists = self.db.query(MenuField.id).filter(
                        MenuField.menu_id == menu_id, MenuField.model == model_name,
                        MenuField.field_name == field['name']).first()
                    if exists:
                        continue
                    data = {
                        'menu': menu_id,
                        'model': model_name,
                        'field_name': field['name'],
                        'title': str(field['title']),
                    }
                    validated = serializer.run_validation(data)
                    serializer.create(validated)
        self.db.commit()
        return DetailResponse(msg="生成成功")
