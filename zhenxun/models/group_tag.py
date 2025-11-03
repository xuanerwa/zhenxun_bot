from tortoise import fields

from zhenxun.services.db_context import Model


class GroupTag(Model):
    """群组标签模型"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增ID"""
    name = fields.CharField(max_length=255, unique=True, description="标签名称")
    """标签名称"""
    description = fields.TextField(null=True, description="标签描述")
    """标签描述"""
    owner_id = fields.CharField(
        max_length=255, null=True, description="创建者ID, null为系统级"
    )
    """创建此标签的用户ID"""
    bot_id = fields.CharField(
        max_length=255, null=True, description="所属Bot ID, null为全局通用"
    )
    """此标签所属的Bot ID"""
    tag_type = fields.CharField(
        max_length=20, default="STATIC", description="标签类型 (STATIC, DYNAMIC)"
    )
    """标签类型"""
    dynamic_rule = fields.TextField(null=True, description="动态标签的计算规则")
    """动态标签的计算规则"""
    is_blacklist = fields.BooleanField(default=False, description="是否为黑名单模式")
    """是否为黑名单模式 (True: 排除模式, False: 包含模式)"""

    groups: fields.ReverseRelation["GroupTagLink"]

    class Meta:  # type: ignore
        table = "group_tags"
        table_description = "群组标签表"


class GroupTagLink(Model):
    """群组与标签的多对多关联模型"""

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增ID"""
    tag = fields.ForeignKeyField(
        "models.GroupTag", related_name="groups", on_delete=fields.CASCADE
    )
    """关联的标签"""
    group_id = fields.CharField(max_length=255, description="群组ID")
    """群组ID"""

    class Meta:  # type: ignore
        table = "group_tag_links"
        table_description = "群组标签关联表"
        unique_together = ("tag", "group_id")
