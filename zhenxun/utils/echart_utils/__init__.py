import os
from pathlib import Path
import random

from zhenxun import ui
from zhenxun.ui.models import BarChartData

from .models import Barh

BACKGROUND_PATH = (
    Path() / "resources" / "themes" / "default" / "assets" / "bar_chart" / "background"
)


class ChartUtils:
    @classmethod
    async def barh(cls, data: Barh) -> bytes:
        """横向统计图"""
        background_image_name = (
            random.choice(os.listdir(BACKGROUND_PATH))
            if BACKGROUND_PATH.exists()
            else None
        )
        chart_component = BarChartData(
            title=data.title,
            category_data=data.category_data,
            data=data.data,
            background_image=background_image_name,
            direction="horizontal",
        )

        return await ui.render(chart_component)
