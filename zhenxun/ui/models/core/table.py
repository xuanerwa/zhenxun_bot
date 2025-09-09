from pathlib import Path
from typing import Literal

from nonebot.compat import field_validator
from pydantic import BaseModel

from ...models.components.progress_bar import ProgressBar
from .base import RenderableComponent
from .text import TextSpan

__all__ = [
    "BaseCell",
    "ImageCell",
    "ProgressBarCell",
    "RichTextCell",
    "StatusBadgeCell",
    "TableCell",
    "TableData",
    "TextCell",
]


class BaseCell(BaseModel):
    """单元格基础模型"""

    type: str


class TextCell(BaseCell):
    """文本单元格"""

    type: Literal["text"] = "text"  # type: ignore
    content: str | float
    bold: bool = False
    color: str | None = None


class ImageCell(BaseCell):
    """图片单元格"""

    type: Literal["image"] = "image"  # type: ignore
    src: str | Path
    width: int = 40
    height: int = 40
    shape: Literal["square", "circle"] = "square"
    alt: str = "image"

    @field_validator("src", mode="before")
    def validate_src(cls, v: str) -> str:
        if isinstance(v, Path):
            v = v.resolve().as_uri()
        return v


class StatusBadgeCell(BaseCell):
    """状态徽章单元格"""

    type: Literal["badge"] = "badge"  # type: ignore
    text: str
    status_type: Literal["ok", "error", "warning", "info"] = "info"


class ProgressBarCell(BaseCell, ProgressBar):
    """进度条单元格，继承ProgressBar模型以复用其字段"""

    type: Literal["progress_bar"] = "progress_bar"  # type: ignore


class RichTextCell(BaseCell):
    """富文本单元格，支持多个带样式的文本片段"""

    type: Literal["rich_text"] = "rich_text"  # type: ignore
    spans: list[TextSpan] = []
    """文本片段列表"""
    direction: Literal["column", "row"] = "column"
    """片段排列方向"""
    gap: str = "4px"
    """片段之间的间距"""


TableCell = (
    TextCell
    | ImageCell
    | StatusBadgeCell
    | ProgressBarCell
    | RichTextCell
    | str
    | int
    | float
    | None
)


class TableData(RenderableComponent):
    """通用表格的数据模型"""

    style_name: str | None = None
    title: str
    """表格主标题"""
    tip: str | None = None
    """表格下方的提示信息"""
    headers: list[str] = []  # noqa: RUF012
    """表头列表"""
    rows: list[list[TableCell]] = []  # noqa: RUF012
    """数据行列表"""
    column_alignments: list[Literal["left", "center", "right"]] | None = None
    """每列的对齐方式"""
    column_widths: list[str | int] | None = None
    """每列的宽度 (e.g., ['50px', 'auto', 100])"""

    @property
    def template_name(self) -> str:
        return "components/core/table"
