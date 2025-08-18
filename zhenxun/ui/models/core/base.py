from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Iterator
from typing import Any

from nonebot.compat import model_dump
from pydantic import BaseModel

from zhenxun.services.renderer.protocols import Renderable

__all__ = ["ContainerComponent", "RenderableComponent"]


class RenderableComponent(BaseModel, Renderable):
    """所有可渲染UI组件的抽象基类。"""

    _is_standalone_template: bool = False

    @property
    def template_name(self) -> str:
        """
        返回用于渲染此组件的Jinja2模板的路径。
        这是一个抽象属性，所有子类都必须覆盖它。
        """
        raise NotImplementedError(
            "Subclasses must implement the 'template_name' property."
        )

    async def prepare(self) -> None:
        """[可选] 生命周期钩子，默认无操作。"""
        pass

    def get_required_scripts(self) -> list[str]:
        """[可选] 返回此组件所需的JS脚本路径列表 (相对于assets目录)。"""
        return []

    def get_required_styles(self) -> list[str]:
        """[可选] 返回此组件所需的CSS样式表路径列表 (相对于assets目录)。"""
        return []

    def get_render_data(self) -> dict[str, Any | Awaitable[Any]]:
        """默认实现，返回模型自身的数据字典。"""
        return model_dump(self)

    def get_extra_css(self, theme_manager: Any) -> str | Awaitable[str]:
        return ""


class ContainerComponent(RenderableComponent, ABC):
    """
    一个为容器类组件设计的抽象基类，封装了预渲染子组件的通用逻辑。
    """

    @abstractmethod
    def _get_renderable_child_items(self) -> Iterator[Any]:
        """
        一个抽象方法，子类必须实现它来返回一个可迭代的对象。
        迭代器中的每个项目都必须具有 'component' 和 'html_content' 属性。
        """
        raise NotImplementedError

    async def prepare(self) -> None:
        """
        通用的 prepare 方法，负责预渲染所有子组件。
        """
        from zhenxun.services import renderer_service

        child_items = list(self._get_renderable_child_items())
        if not child_items:
            return

        components_to_render = [
            item.component for item in child_items if item.component
        ]

        prepare_tasks = [
            comp.prepare() for comp in components_to_render if hasattr(comp, "prepare")
        ]
        if prepare_tasks:
            await asyncio.gather(*prepare_tasks)

        render_tasks = [
            renderer_service.render_to_html(comp) for comp in components_to_render
        ]
        rendered_htmls = await asyncio.gather(*render_tasks)

        for item, html in zip(child_items, rendered_htmls):
            item.html_content = html
