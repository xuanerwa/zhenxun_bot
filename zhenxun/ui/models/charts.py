from typing import Literal

from pydantic import BaseModel


class BaseChartData(BaseModel):
    """所有图表数据模型的基类"""

    style_name: str | None = None
    title: str


class BarChartData(BaseChartData):
    """柱状图（支持横向和竖向）的数据模型"""

    category_data: list[str]
    data: list[int | float]
    direction: Literal["horizontal", "vertical"] = "horizontal"
    background_image: str | None = None


class PieChartDataItem(BaseModel):
    name: str
    value: int | float


class PieChartData(BaseChartData):
    """饼图的数据模型"""

    data: list[PieChartDataItem]


class LineChartSeries(BaseModel):
    name: str
    data: list[int | float]
    smooth: bool = False


class LineChartData(BaseChartData):
    """折线图的数据模型"""

    category_data: list[str]
    series: list[LineChartSeries]
