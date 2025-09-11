from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel

from .base import ContainerComponent, RenderableComponent

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
    """元素的文本内容 (用于标题、段落、引用)"""
    level: int | None = None
    """标题的级别 (1-4)"""
    src: str | None = None
    """图片的来源 (URL或data URI)"""
    caption: str | None = None
    """图片的说明文字"""
    code: str | None = None
    """代码块的内容"""
    language: str | None = None
    """代码块的语言"""
    data: list[str] | None = None
    """列表项的内容列表"""
    ordered: bool | None = None
    """是否为有序列表"""
    component: RenderableComponent | None = None
    """嵌入的自定义可渲染组件"""


class NotebookData(ContainerComponent):
    """Notebook转图片的数据模型"""

    style_name: str | None = None
    """Notebook的样式名称"""
    elements: list[NotebookElement]
    """构成Notebook页面的元素列表"""

    @property
    def template_name(self) -> str:
        return "components/core/notebook"

    def get_children(self) -> Iterable[RenderableComponent]:
        for element in self.elements:
            if element.type == "component" and element.component:
                yield element.component
