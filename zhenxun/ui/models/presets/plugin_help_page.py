from pydantic import BaseModel

from ..core.base import RenderableComponent

__all__ = [
    "HelpCategory",
    "HelpItem",
    "PluginHelpPageData",
]


class HelpItem(BaseModel):
    """帮助菜单中的单个功能项"""

    name: str
    """功能名称"""
    description: str
    """功能描述"""
    usage: str
    """功能用法说明"""


class HelpCategory(BaseModel):
    """帮助菜单中的一个功能类别"""

    title: str
    """分类标题"""
    icon_svg_path: str
    """分类图标的SVG路径数据"""
    items: list[HelpItem]
    """该分类下的功能项列表"""


class PluginHelpPageData(RenderableComponent):
    """通用插件帮助页面的数据模型"""

    style_name: str | None = None
    """页面样式名称"""
    bot_nickname: str
    """机器人昵称"""
    page_title: str
    """页面主标题"""
    categories: list[HelpCategory]
    """帮助分类列表"""

    @property
    def template_name(self) -> str:
        return "pages/core/plugin_help_page"
