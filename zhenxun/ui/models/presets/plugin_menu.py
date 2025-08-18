from pydantic import BaseModel, Field

from ..core.base import RenderableComponent

__all__ = [
    "PluginMenuCategory",
    "PluginMenuData",
    "PluginMenuItem",
]


class PluginMenuItem(BaseModel):
    """插件菜单中的单个插件项"""

    id: str
    name: str
    status: bool
    has_superuser_help: bool
    commands: list[str] = Field(default_factory=list)


class PluginMenuCategory(BaseModel):
    """插件菜单中的一个分类"""

    name: str
    items: list[PluginMenuItem]


class PluginMenuData(RenderableComponent):
    """通用插件帮助菜单的数据模型"""

    style_name: str | None = None
    bot_name: str
    bot_avatar_url: str
    is_detail: bool
    plugin_count: int
    active_count: int
    categories: list[PluginMenuCategory]

    @property
    def template_name(self) -> str:
        return "pages/core/plugin_menu"
