from typing import Any, Generic, Literal, TypeVar
from typing_extensions import Self

from ..models.charts import (
    BarChartData,
    BaseChartData,
    LineChartData,
    LineChartSeries,
    PieChartData,
    PieChartDataItem,
)
from .base import BaseBuilder

T_ChartData = TypeVar("T_ChartData", bound=BaseChartData)


class BaseChartBuilder(BaseBuilder[T_ChartData], Generic[T_ChartData]):
    """所有图表构建器的基类"""

    def set_title(self, title: str) -> Self:
        self._data.title = title
        return self


class BarChartBuilder(BaseChartBuilder[BarChartData]):
    """链式构建柱状图的辅助类 (支持横向和竖向)"""

    def __init__(
        self, title: str, direction: Literal["horizontal", "vertical"] = "horizontal"
    ):
        data_model = BarChartData(
            title=title, direction=direction, category_data=[], data=[]
        )
        super().__init__(data_model, template_name="components/charts/bar_chart")

    def add_data(self, category: str, value: float) -> Self:
        """添加一个数据点"""
        self._data.category_data.append(category)
        self._data.data.append(value)
        return self

    def add_data_items(
        self, items: list[tuple[str, int | float]] | list[dict[str, Any]]
    ) -> Self:
        for item in items:
            if isinstance(item, tuple):
                self.add_data(item[0], item[1])
            elif isinstance(item, dict):
                self.add_data(item.get("category", ""), item.get("value", 0))
        return self

    def set_background_image(self, background_image: str) -> Self:
        """设置背景图片 (仅横向柱状图模板支持)"""
        self._data.background_image = background_image
        return self


class PieChartBuilder(BaseChartBuilder[PieChartData]):
    """链式构建饼图的辅助类"""

    def __init__(self, title: str):
        data_model = PieChartData(title=title, data=[])
        super().__init__(data_model, template_name="components/charts/pie_chart")

    def add_slice(self, name: str, value: float) -> Self:
        """添加一个饼图扇区"""
        self._data.data.append(PieChartDataItem(name=name, value=value))
        return self


class LineChartBuilder(BaseChartBuilder[LineChartData]):
    """链式构建折线图的辅助类"""

    def __init__(self, title: str):
        data_model = LineChartData(title=title, category_data=[], series=[])
        super().__init__(data_model, template_name="components/charts/line_chart")

    def set_categories(self, categories: list[str]) -> Self:
        """设置X轴的分类标签"""
        self._data.category_data = categories
        return self

    def add_series(
        self, name: str, data: list[int | float], smooth: bool = False
    ) -> Self:
        """添加一条折线"""
        self._data.series.append(LineChartSeries(name=name, data=data, smooth=smooth))
        return self
