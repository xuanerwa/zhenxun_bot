from pathlib import Path

from nonebot_plugin_htmlrender import html_to_pic

from .protocols import ScreenshotEngine


class PlaywrightEngine(ScreenshotEngine):
    """使用 nonebot-plugin-htmlrender 实现的截图引擎。"""

    async def render(self, html: str, base_url_path: Path, **render_options) -> bytes:
        base_url_for_browser = base_url_path.absolute().as_uri()
        if not base_url_for_browser.endswith("/"):
            base_url_for_browser += "/"

        final_render_options = {
            "viewport": {"width": 800, "height": 10},
            **render_options,
            "base_url": base_url_for_browser,
        }

        return await html_to_pic(
            html=html,
            template_path=base_url_for_browser,
            **final_render_options,
        )


def get_screenshot_engine() -> ScreenshotEngine:
    """
    截图引擎工厂函数。
    目前只返回 PlaywrightEngine, 未来可以根据配置返回不同的引擎。
    """
    return PlaywrightEngine()
