from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["Divider", "Rectangle"]


class Divider(RenderableComponent):
    """一个简单的分割线组件。"""

    component_type: Literal["divider"] = "divider"
    margin: str = Field("2em 0", description="CSS margin属性，控制分割线上下的间距")
    color: str = Field("#f7889c", description="分割线颜色")
    style: Literal["solid", "dashed", "dotted"] = Field("solid", description="线条样式")
    thickness: str = Field("1px", description="线条粗细")

    @property
    def template_name(self) -> str:
        return "components/widgets/divider"


class Rectangle(RenderableComponent):
    """一个矩形背景块组件。"""

    component_type: Literal["rectangle"] = "rectangle"
    height: str = Field("50px", description="矩形的高度 (CSS value)")
    background_color: str = Field("#fdf1f5", description="背景颜色")
    border: str = Field("1px solid #fce4ec", description="CSS border属性")
    border_radius: str = Field("8px", description="CSS border-radius属性")

    @property
    def template_name(self) -> str:
        return "components/widgets/rectangle"
