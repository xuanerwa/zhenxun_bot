import builtins
from pathlib import Path

from ...models.core.base import RenderableComponent
from ...models.core.notebook import NotebookData, NotebookElement
from ..base import BaseBuilder

__all__ = ["NotebookBuilder"]


class NotebookBuilder(BaseBuilder[NotebookData]):
    """
    一个用于链式构建 Notebook 页面的辅助类。
    """

    def __init__(self, data: list[NotebookElement] | None = None):
        elements = data if data is not None else []
        data_model = NotebookData(elements=elements)
        super().__init__(data_model, template_name="components/core/notebook")
        self._elements = elements

    def text(self, text: str) -> "NotebookBuilder":
        """添加Notebook文本"""
        self._elements.append(NotebookElement(type="paragraph", text=text))
        return self

    def head(self, text: str, level: int = 1) -> "NotebookBuilder":
        """添加Notebook标题"""
        if not 1 <= level <= 4:
            raise ValueError("标题级别必须在1-4之间")
        self._elements.append(NotebookElement(type="heading", text=text, level=level))
        return self

    def image(
        self,
        content: str,
        caption: str | None = None,
    ) -> "NotebookBuilder":
        """添加Notebook图片"""
        src = ""
        if isinstance(content, Path):
            src = content.absolute().as_uri()
        elif content.startswith("base64"):
            src = f"data:image/png;base64,{content.split('base64://', 1)[-1]}"
        else:
            src = content
        self._elements.append(NotebookElement(type="image", src=src, caption=caption))
        return self

    def quote(self, text: str | list[str]) -> "NotebookBuilder":
        """添加Notebook引用文本"""
        if isinstance(text, str):
            self._elements.append(NotebookElement(type="blockquote", text=text))
        elif isinstance(text, list):
            for t in text:
                self._elements.append(NotebookElement(type="blockquote", text=t))
        return self

    def code(self, code: str, language: str = "python") -> "NotebookBuilder":
        """添加Notebook代码块"""
        self._elements.append(
            NotebookElement(type="code", code=code, language=language)
        )
        return self

    def list(self, items: list[str], ordered: bool = False) -> "NotebookBuilder":
        """添加Notebook列表"""
        self._elements.append(NotebookElement(type="list", data=items, ordered=ordered))
        return self

    def add_divider(self, **kwargs) -> "NotebookBuilder":
        """
        添加分隔线。
        :param kwargs: Divider组件的可选参数, 如 margin, color, style, thickness。
        """
        from ...models.components import Divider

        self.add_component(Divider(**kwargs))
        return self

    def add_component(self, component: RenderableComponent) -> "NotebookBuilder":
        """向 Notebook 中添加一个可渲染的自定义组件。"""
        self._elements.append(
            NotebookElement(type="component", component_data=component)
        )
        return self

    def add_texts(self, texts: builtins.list[str]) -> "NotebookBuilder":
        """批量添加多个文本段落"""
        for text in texts:
            self.text(text)
        return self

    def add_quotes(self, quotes: builtins.list[str]) -> "NotebookBuilder":
        """批量添加引用"""
        for quote in quotes:
            self.quote(quote)
        return self

    async def build(
        self, use_cache: bool = False, frameless: bool = False, **render_options
    ) -> bytes:
        """构建Notebook图片"""
        self._data.elements = self._elements
        return await super().build(
            use_cache=use_cache, frameless=frameless, **render_options
        )
