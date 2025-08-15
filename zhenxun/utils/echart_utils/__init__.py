import os
from pathlib import Path
import random

from zhenxun.services import renderer_service
from zhenxun.utils._build_image import BuildImage

from .models import Barh

BACKGROUND_PATH = (
    Path() / "resources" / "themes" / "default" / "assets" / "bar_chart" / "background"
)


class ChartUtils:
    @classmethod
    async def barh(cls, data: Barh) -> BuildImage:
        """横向统计图"""
        background_image_name = random.choice(os.listdir(BACKGROUND_PATH))
        render_data = {
            "title": data.title,
            "category_data": data.category_data,
            "data": data.data,
            "background_image": background_image_name,
            "direction": "horizontal",
        }

        image_bytes = await renderer_service.render(
            "components/charts/bar_chart", data=render_data
        )
        return BuildImage.open(image_bytes)
