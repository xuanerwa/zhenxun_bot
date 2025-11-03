"""
标签服务入口，提供 ``TagManager`` 实例并加载内置规则。
"""

from .manager import TagManager

tag_manager = TagManager()

from . import filters  # noqa: F401

__all__ = ["tag_manager"]
