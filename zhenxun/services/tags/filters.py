"""
动态标签的内置过滤器集合，可通过装饰器注册到标签管理器。
"""

from . import tag_manager

tag_manager.add_field_rule("member_count", db_field="member_count", value_type=int)
tag_manager.add_field_rule("level", db_field="level", value_type=int)
tag_manager.add_field_rule("status", db_field="status", value_type=bool)
tag_manager.add_field_rule("is_super", db_field="is_super", value_type=bool)
tag_manager.add_field_rule("group_name", db_field="group_name", value_type=str)
