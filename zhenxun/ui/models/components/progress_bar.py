from typing import Literal

from pydantic import Field

from ..core.base import RenderableComponent

__all__ = ["ProgressBar"]


class ProgressBar(RenderableComponent):
    """一个进度条组件。"""

    component_type: Literal["progress_bar"] = "progress_bar"
    progress: float = Field(..., ge=0, le=100, description="进度百分比 (0-100)")
    label: str | None = Field(default=None, description="显示在进度条上的可选文本")
    color_scheme: Literal["primary", "success", "warning", "error", "info"] = Field(
        default="primary",
        description="预设的颜色方案",
    )
    animated: bool = Field(default=False, description="是否显示动画效果")

    @property
    def template_name(self) -> str:
        return "components/widgets/progress_bar"
