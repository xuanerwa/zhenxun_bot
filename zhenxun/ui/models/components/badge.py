from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["Badge"]


class Badge(RenderableComponent):
    """一个简单的徽章组件，用于显示状态或标签。"""

    component_type: Literal["badge"] = "badge"
    text: str = Field(..., description="徽章上显示的文本")
    color_scheme: Literal["primary", "success", "warning", "error", "info"] = Field(
        default="info",
        description="预设的颜色方案",
    )

    @property
    def template_name(self) -> str:
        return "components/widgets/badge"
