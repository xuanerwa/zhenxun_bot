from typing import Generic, TypeVar
from typing_extensions import Self

from pydantic import BaseModel

from zhenxun.services import renderer_service

T_DataModel = TypeVar("T_DataModel", bound=BaseModel)


class BaseBuilder(Generic[T_DataModel]):
    """所有UI构建器的基类，提供通用的样式化和构建逻辑。"""

    def __init__(self, data_model: T_DataModel, template_name: str):
        self._data: T_DataModel = data_model
        self._style_name: str | None = None
        self._template_name = template_name

    def with_style(self, style_name: str) -> Self:
        """
        为组件应用一个特定的样式。
        """
        self._style_name = style_name
        return self

    async def build(self, use_cache: bool = False, **render_options) -> bytes:
        """
        通用的构建方法，将数据渲染为图片。
        """
        if self._style_name and hasattr(self._data, "style_name"):
            setattr(self._data, "style_name", self._style_name)

        data_to_render = self._data

        return await renderer_service.render(
            template_name=self._template_name,
            data=data_to_render,
            use_cache=use_cache,
            style_name=self._style_name,
            **render_options,
        )
