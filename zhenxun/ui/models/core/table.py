from typing import Literal

from pydantic import BaseModel, Field

from .base import RenderableComponent

__all__ = [
    "BaseCell",
    "ImageCell",
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
    content: str
    bold: bool = False
    color: str | None = None


class ImageCell(BaseCell):
    """图片单元格"""

    type: Literal["image"] = "image"  # type: ignore
    src: str
    width: int = 40
    height: int = 40
    shape: Literal["square", "circle"] = "square"
    alt: str = "image"


class StatusBadgeCell(BaseCell):
    """状态徽章单元格"""

    type: Literal["badge"] = "badge"  # type: ignore
    text: str
    status_type: Literal["ok", "error", "warning", "info"] = "info"


TableCell = TextCell | ImageCell | StatusBadgeCell | str | int | float | None


class TableData(RenderableComponent):
    """通用表格的数据模型"""

    style_name: str | None = None
    title: str = Field(..., description="表格主标题")
    tip: str | None = Field(None, description="表格下方的提示信息")
    headers: list[str] = Field(default_factory=list, description="表头列表")
    rows: list[list[TableCell]] = Field(default_factory=list, description="数据行列表")

    @property
    def template_name(self) -> str:
        return "components/core/table"
