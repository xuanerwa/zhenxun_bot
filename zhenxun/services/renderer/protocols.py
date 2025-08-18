from abc import ABC, abstractmethod
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel


class Renderable(ABC):
    """
    一个协议，定义了任何可被渲染的UI组件必须具备的形态。
    """

    @property
    @abstractmethod
    def template_name(self) -> str:
        """组件声明它需要哪个模板文件。"""
        ...

    async def prepare(self) -> None:
        """
        [可选] 一个生命周期钩子，用于在渲染前执行异步数据获取和预处理。
        """
        pass

    def get_required_scripts(self) -> list[str]:
        """[可选] 返回此组件所需的JS脚本路径列表 (相对于assets目录)。"""
        return []

    def get_required_styles(self) -> list[str]:
        """[可选] 返回此组件所需的CSS样式表路径列表 (相对于assets目录)。"""
        return []

    @abstractmethod
    def get_render_data(self) -> dict[str, Any | Awaitable[Any]]:
        """
        返回一个将传递给模板的数据字典。
        重要：字典的值可以是协程(Awaitable)，渲染服务会自动解析它们。
        """
        ...

    def get_extra_css(self, theme_manager: Any) -> str | Awaitable[str]:
        """
        [可选] 一个生命周期钩子，让组件可以提供额外的CSS。
        可以返回 str 或 awaitable[str]。
        """
        return ""


class ScreenshotEngine(Protocol):
    """
    一个协议，定义了截图引擎的核心能力。
    """

    async def render(self, html: str, base_url_path: Path, **render_options) -> bytes:
        """
        将HTML字符串截图为图片。

        参数:
            html: 要渲染的HTML内容。
            base_url_path: 用于解析相对路径（如CSS, JS, 图片）的基础URL路径。
            **render_options: 传递给底层截图库的额外选项 (如 viewport)。
        """
        ...


class RenderResult(BaseModel):
    """
    渲染服务的统一返回类型。
    """

    image_bytes: bytes | None = None
    html_content: str | None = None
