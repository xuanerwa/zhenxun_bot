import base64
from typing import Any
from typing_extensions import Self

from ...models.core.layout import LayoutData, LayoutItem
from ..base import BaseBuilder

__all__ = ["LayoutBuilder"]


class LayoutBuilder(BaseBuilder[LayoutData]):
    """
    一个用于将多个图片（bytes）组合成单张图片的链式构建器。
    采用混合模式，提供便捷的工厂方法和灵活的自定义模板能力。
    """

    def __init__(self):
        super().__init__(LayoutData(), template_name="")
        self._items: list[LayoutItem] = []
        self._options: dict[str, Any] = {}
        self._preset_template_name: str | None = None

    @classmethod
    def column(cls, **options: Any) -> Self:
        """
        工厂方法：创建一个垂直列布局的构建器。
        :param options: 传递给模板的选项，如 gap, padding, align_items 等。
        """
        builder = cls()
        builder._preset_template_name = "layouts/column"
        builder._options.update(options)
        return builder

    @classmethod
    def grid(cls, **options: Any) -> Self:
        """
        工厂方法：创建一个网格布局的构建器。
        :param options: 传递给模板的选项，如 columns, gap, padding 等。
        """
        builder = cls()
        builder._preset_template_name = "layouts/grid"
        builder._options.update(options)
        return builder

    @classmethod
    def vstack(cls, images: list[bytes], **options: Any) -> Self:
        """
        工厂方法：创建一个垂直堆叠布局的构建器，并直接添加图片。

        参数:
            images: 要垂直堆叠的图片字节流列表。
            options: 传递给模板的选项，如 gap, padding, align_items 等。
        """
        builder = cls.column(**options)
        for image_bytes in images:
            builder.add_item(image_bytes)
        return builder

    @classmethod
    def hstack(cls, images: list[bytes], **options: Any) -> Self:
        """
        工厂方法：创建一个水平堆叠布局的构建器，并直接添加图片。

        参数:
            images: 要水平堆叠的图片字节流列表。
            options: 传递给模板的选项，如 gap, padding, align_items 等。
        """
        builder = cls()
        builder._preset_template_name = "layouts/row"
        builder._options.update(options)
        for image_bytes in images:
            builder.add_item(image_bytes)
        return builder

    def add_item(
        self, image_bytes: bytes, metadata: dict[str, Any] | None = None
    ) -> Self:
        """
        向布局中添加一个图片项目。
        :param image_bytes: 图片的原始字节数据。
        :param metadata: (可选) 与此项目关联的元数据，可用于模板。
        """
        b64_string = base64.b64encode(image_bytes).decode("utf-8")
        src = f"data:image/png;base64,{b64_string}"
        self._items.append(LayoutItem(src=src, metadata=metadata))
        return self

    def add_option(self, key: str, value: Any) -> Self:
        """
        为布局添加一个自定义选项，该选项会传递给模板。
        """
        self._options[key] = value
        return self

    async def build(
        self, use_cache: bool = False, template: str | None = None, **render_options
    ) -> bytes:
        """
        构建最终的布局图片。
        :param use_cache: 是否使用缓存。
        :param template: (可选) 强制使用指定的模板，覆盖工厂方法的预设。
                         这是实现自定义布局的关键。
        :param render_options: 传递给渲染引擎的额外选项。
        """
        final_template_name = template or self._preset_template_name

        if not final_template_name:
            raise ValueError(
                "必须通过工厂方法 (如 LayoutBuilder.column()) 或在 build() "
                "方法中提供一个模板名称。"
            )

        self._data.items = self._items
        self._data.options = self._options
        self._template_name = final_template_name

        return await super().build(use_cache=use_cache, **render_options)
