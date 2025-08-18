from typing import Any
from typing_extensions import Self

from ...models.core.base import RenderableComponent
from ...models.core.layout import LayoutData, LayoutItem
from ..base import BaseBuilder

__all__ = ["LayoutBuilder"]


class LayoutBuilder(BaseBuilder[LayoutData]):
    """
    一个用于将多个UI组件组合成单张图片的链式构建器。
    它通过在单个渲染流程中动态包含子模板来实现高质量的输出。
    """

    def __init__(self):
        super().__init__(LayoutData(), template_name="")
        self._options: dict[str, Any] = {}

    @classmethod
    def column(cls, **options: Any) -> Self:
        builder = cls()
        builder._template_name = "layouts/column"
        builder._options.update(options)
        return builder

    @classmethod
    def row(cls, **options: Any) -> Self:
        builder = cls()
        builder._template_name = "layouts/row"
        builder._options.update(options)
        return builder

    @classmethod
    def hstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        builder = cls.row(**options)
        for component in components:
            builder.add_item(component)
        return builder

    @classmethod
    def vstack(
        cls, components: list["BaseBuilder | RenderableComponent"], **options: Any
    ) -> Self:
        builder = cls.column(**options)
        for component in components:
            builder.add_item(component)
        return builder

    def add_item(
        self,
        component: "BaseBuilder | RenderableComponent",
        metadata: dict[str, Any] | None = None,
    ) -> Self:
        """
        向布局中添加一个组件，支持多种组件类型的添加。

        参数:
            component: 一个 Builder 实例 (如 TableBuilder) 或一个 RenderableComponent
                      数据模型。
            metadata: (可选) 与此项目关联的元数据，可用于模板。

        返回:
            Self: 返回当前布局构建器实例，支持链式调用。
        """
        component_data = (
            component.data if isinstance(component, BaseBuilder) else component
        )
        self._data.children.append(
            LayoutItem(component=component_data, metadata=metadata)
        )
        return self

    def add_option(self, key: str, value: Any) -> Self:
        """
        为布局添加一个自定义选项，该选项会传递给模板。

        参数:
            key: 选项的键名，用于在模板中引用。
            value: 选项的值，可以是任意类型的数据。

        返回:
            Self: 返回当前布局构建器实例，支持链式调用。
        """
        self._options[key] = value
        return self

    def build(self) -> LayoutData:
        """
        [修改] 构建并返回 LayoutData 模型实例。
        此方法现在是同步的，并且不执行渲染。

        参数:
            无

        返回:
            LayoutData: 配置好的布局数据模型。
        """
        if not self._template_name:
            raise ValueError(
                "必须通过工厂方法 (如 LayoutBuilder.column()) 初始化布局类型。"
            )

        self._data.options = self._options
        self._data.layout_type = self._template_name.split("/")[-1]
        return self._data
