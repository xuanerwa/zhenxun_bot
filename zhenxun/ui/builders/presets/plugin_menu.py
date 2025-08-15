from ...models.presets.plugin_menu import (
    PluginMenuCategory,
    PluginMenuData,
)
from ..base import BaseBuilder

__all__ = ["PluginMenuBuilder"]


class PluginMenuBuilder(BaseBuilder[PluginMenuData]):
    """链式构建插件菜单的辅助类"""

    def __init__(self, bot_name: str, bot_avatar_url: str, is_detail: bool = False):
        self._data = PluginMenuData(
            bot_name=bot_name,
            bot_avatar_url=bot_avatar_url,
            is_detail=is_detail,
            plugin_count=0,
            active_count=0,
            categories=[],
        )

        super().__init__(self._data, template_name="pages/core/plugin_menu")

    def add_category(self, category: PluginMenuCategory) -> "PluginMenuBuilder":
        self._data.categories.append(category)
        self._data.plugin_count += len(category.items)
        self._data.active_count += sum(1 for item in category.items if item.status)
        return self

    def add_categories(
        self, categories: list[PluginMenuCategory]
    ) -> "PluginMenuBuilder":
        for category in categories:
            self.add_category(category)
        return self
