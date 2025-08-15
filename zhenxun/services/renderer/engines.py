from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles
from jinja2 import Environment
import markdown
from nonebot_plugin_htmlrender import html_to_pic
from pydantic import BaseModel

from zhenxun.configs.path_config import THEMES_PATH
from zhenxun.services.log import logger

from .models import Theme

THEME_PATH = THEMES_PATH
RESOURCE_ROOT = THEMES_PATH.parent


class BaseEngine(ABC):
    """渲染引擎的抽象基类。"""

    @abstractmethod
    async def render(
        self,
        template_name: str,
        data: BaseModel | dict | None,
        theme: Theme,
        jinja_env: "Environment | None" = None,
        extra_css_paths: list[Path] | None = None,
        custom_css_path: Path | None = None,
        **kwargs,
    ) -> bytes:
        """所有引擎都必须实现的渲染方法。"""
        pass


class BaseHtmlRenderingEngine(BaseEngine):
    """
    一个专门用于处理HTML到图片转换的引擎基类。
    它使用模板方法模式，定义了渲染的固定流程，
    并将具体的HTML内容生成委托给子类的抽象方法 `get_html_content`。
    """

    @abstractmethod
    async def get_html_content(
        self,
        template_name: str,
        data: BaseModel | dict | None,
        theme: Theme,
        jinja_env: "Environment",
        extra_css_paths: list[Path] | None,
        custom_css_path: Path | None,
        frameless: bool,
        **kwargs,
    ) -> str:
        """
        [抽象方法] 子类必须实现此方法以生成最终的HTML字符串。
        """
        pass

    async def render(
        self,
        template_name: str,
        data: BaseModel | dict | None,
        theme: Theme,
        jinja_env: "Environment | None" = None,
        extra_css_paths: list[Path] | None = None,
        custom_css_path: Path | None = None,
        **kwargs,
    ) -> bytes:
        """
        [通用渲染流程] 调用 `get_html_content` 获取HTML，然后调用 `html_to_pic` 生成图片
        """
        if not jinja_env:
            raise ValueError("HTML渲染器需要一个有效的Jinja2环境实例。")

        frameless = kwargs.pop("frameless", False)

        html_content = await self.get_html_content(
            template_name,
            data,
            theme,
            jinja_env,
            extra_css_paths,
            custom_css_path,
            frameless=frameless,
            **kwargs,
        )

        base_url_for_browser = RESOURCE_ROOT.absolute().as_uri()
        if not base_url_for_browser.endswith("/"):
            base_url_for_browser += "/"

        pages_config = {
            "viewport": kwargs.pop("viewport", {"width": 800, "height": 10}),
            "base_url": base_url_for_browser,
        }

        final_screenshot_kwargs = kwargs.copy()
        final_screenshot_kwargs.update(pages_config)

        return await html_to_pic(
            html=html_content,
            template_path=base_url_for_browser,
            **final_screenshot_kwargs,
        )


class HtmlRenderer(BaseHtmlRenderingEngine):
    """使用 nonebot-plugin-htmlrender 渲染HTML模板的引擎。"""

    async def get_html_content(
        self,
        template_name: str,
        data: BaseModel | dict | None,
        theme: Theme,
        jinja_env: "Environment",
        extra_css_paths: list[Path] | None,
        custom_css_path: Path | None,
        frameless: bool,
        **kwargs,
    ) -> str:
        def asset_loader(asset_path: str) -> str:
            current_theme_asset = theme.assets_dir / asset_path
            if current_theme_asset.exists():
                return current_theme_asset.relative_to(RESOURCE_ROOT).as_posix()

            default_theme_asset = theme.default_assets_dir / asset_path
            if default_theme_asset.exists():
                return default_theme_asset.relative_to(RESOURCE_ROOT).as_posix()

            logger.warning(
                f"资源文件在主题 '{theme.name}' 和 'default' 中均未找到: {asset_path}"
            )
            return ""

        extra_css_content = ""
        if extra_css_paths:
            css_contents = []
            for path in extra_css_paths:
                if path.exists():
                    async with aiofiles.open(path, encoding="utf-8") as f:
                        css_contents.append(await f.read())
            extra_css_content = "\n".join(css_contents)

        template_context = {
            "data": data,
            "extra_css": extra_css_content,
            "frameless": frameless,
            "theme": {
                "name": theme.name,
                "palette": theme.palette,
                "asset": asset_loader,
            },
        }

        template = jinja_env.get_template(template_name)
        return await template.render_async(**template_context)


class MarkdownEngine(BaseHtmlRenderingEngine):
    """在服务端渲染 Markdown 为 HTML，然后截图的引擎。"""

    async def get_html_content(
        self,
        template_name: str,
        data: BaseModel | dict | None,
        theme: Theme,
        jinja_env: "Environment",
        extra_css_paths: list[Path] | None,
        custom_css_path: Path | None,
        frameless: bool,
        **kwargs,
    ) -> str:
        if isinstance(data, BaseModel):
            raw_md = getattr(data, "markdown", "") if hasattr(data, "markdown") else ""
        else:
            raw_md = (data or {}).get("markdown", "")

        md_html = markdown.markdown(
            raw_md,
            extensions=[
                "pymdownx.tasklist",
                "tables",
                "fenced_code",
                "codehilite",
                "mdx_math",
                "pymdownx.tilde",
            ],
            extension_configs={"mdx_math": {"enable_dollar_delimiter": True}},
        )

        final_css_content = ""
        if custom_css_path and custom_css_path.exists():
            logger.debug(f"正在为 Markdown 渲染加载自定义样式: {custom_css_path}")
            async with aiofiles.open(custom_css_path, encoding="utf-8") as f:
                final_css_content = await f.read()
        else:
            css_paths = [
                theme.default_assets_dir / "css/markdown/github-light.css",
                theme.default_assets_dir / "css/markdown/pygments-default.css",
            ]
            css_contents = []
            for path in css_paths:
                if path.exists():
                    async with aiofiles.open(path, encoding="utf-8") as f:
                        css_contents.append(await f.read())
            final_css_content = "\n".join(css_contents)

        template_context = {
            "data": data,
            "theme_css": theme.style_css,
            "custom_style_css": final_css_content,
            "md_html": md_html,
            "extra_css": "",
            "frameless": frameless,
            "theme": {"name": theme.name},
        }

        template = jinja_env.get_template(template_name)
        return await template.render_async(**template_context)
