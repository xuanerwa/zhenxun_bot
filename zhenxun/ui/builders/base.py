from typing import Generic, TypeVar
from typing_extensions import Self

from pydantic import BaseModel

T_DataModel = TypeVar("T_DataModel", bound=BaseModel)


class BaseBuilder(Generic[T_DataModel]):
    """所有UI构建器的基类，提供通用的样式化和构建逻辑。"""

    def __init__(self, data_model: T_DataModel, template_name: str):
        self._data: T_DataModel = data_model
        self._style_name: str | None = None
        self._template_name = template_name
        self._inline_style: dict | None = None
        self._extra_css: str | None = None

    @property
    def data(self) -> T_DataModel:
        return self._data

    def with_style(self, style_name: str) -> Self:
        """
        为组件应用一个特定的样式。
        """
        self._style_name = style_name
        return self

    def with_inline_style(self, style: dict[str, str]) -> Self:
        """
        为组件的根元素应用动态的内联样式。

        参数:
            style: 一个CSS样式字典，例如 {"background-color":"#fff","font-size":"16px"}
        """
        self._inline_style = style
        return self

    def with_extra_css(self, css: str) -> Self:
        """
        向页面注入一段自定义的CSS样式字符串。

        参数:
            css: 包含CSS规则的字符串。
        """
        self._extra_css = css
        return self

    def build(self) -> T_DataModel:
        """
        构建并返回配置好的数据模型。
        """
        if self._style_name and hasattr(self._data, "style_name"):
            setattr(self._data, "style_name", self._style_name)

        return self._data
