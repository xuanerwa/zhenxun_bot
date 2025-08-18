from typing import Literal
import uuid

from pydantic import BaseModel, Field

from .core.base import RenderableComponent


class BaseChartData(RenderableComponent):
    """所有图表数据模型的基类"""

    style_name: str | None = None
    title: str
    chart_id: str = Field(default_factory=lambda: f"chart-{uuid.uuid4().hex}")

    def get_required_scripts(self) -> list[str]:
        """声明此组件需要 ECharts 库。"""
        return ["js/echarts.min.js"]


class BarChartData(BaseChartData):
    """柱状图（支持横向和竖向）的数据模型"""

    category_data: list[str]
    data: list[int | float]
    direction: Literal["horizontal", "vertical"] = "horizontal"
    background_image: str | None = None

    @property
    def template_name(self) -> str:
        return "components/charts/bar_chart"


class PieChartDataItem(BaseModel):
    name: str
    value: int | float


class PieChartData(BaseChartData):
    """饼图的数据模型"""

    data: list[PieChartDataItem]

    @property
    def template_name(self) -> str:
        return "components/charts/pie_chart"


class LineChartSeries(BaseModel):
    name: str
    data: list[int | float]
    smooth: bool = False


class LineChartData(BaseChartData):
    """折线图的数据模型"""

    category_data: list[str]
    series: list[LineChartSeries]

    @property
    def template_name(self) -> str:
        return "components/charts/line_chart"
