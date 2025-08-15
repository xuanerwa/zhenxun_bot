from typing import Literal

from pydantic import BaseModel

from .base import RenderableComponent

__all__ = ["NotebookData", "NotebookElement"]


class NotebookElement(BaseModel):
    """一个 Notebook 页面中的单个元素"""

    type: Literal[
        "heading",
        "paragraph",
        "image",
        "blockquote",
        "code",
        "list",
        "divider",
        "component",
    ]
    text: str | None = None
    level: int | None = None
    src: str | None = None
    caption: str | None = None
    code: str | None = None
    language: str | None = None
    data: list[str] | None = None
    ordered: bool | None = None
    component_data: RenderableComponent | None = None


class NotebookData(BaseModel):
    """Notebook转图片的数据模型"""

    style_name: str | None = None
    elements: list[NotebookElement]
