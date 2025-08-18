from collections.abc import Callable
import inspect
from pathlib import Path
from typing import Any

import aiofiles
from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
    TemplateNotFound,
    select_autoescape,
)
import markdown
from pydantic import BaseModel
import ujson as json

from zhenxun.configs.path_config import THEMES_PATH
from zhenxun.services.log import logger
from zhenxun.services.renderer.models import TemplateManifest
from zhenxun.services.renderer.protocols import Renderable
from zhenxun.utils.exception import RenderingError
from zhenxun.utils.pydantic_compat import model_dump


class Theme(BaseModel):
    name: str
    palette: dict[str, Any]
    style_css: str = ""
    assets_dir: Path
    default_assets_dir: Path


class ThemeManager:
    def __init__(
        self,
        plugin_template_paths: dict[str, Path],
        custom_filters: dict[str, Callable],
        custom_globals: dict[str, Callable],
        markdown_styles: dict[str, Path],
    ):
        prefix_loader = PrefixLoader(
            {
                namespace: FileSystemLoader(str(path.absolute()))
                for namespace, path in plugin_template_paths.items()
            }
        )
        theme_loader = FileSystemLoader(
            [
                str(THEMES_PATH / "current_theme_placeholder" / "templates"),
                str(THEMES_PATH / "default" / "templates"),
            ]
        )
        final_loader = ChoiceLoader([prefix_loader, theme_loader])

        self.jinja_env = Environment(
            loader=final_loader,
            enable_async=True,
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.current_theme: Theme | None = None
        self._custom_filters = custom_filters
        self._custom_globals = custom_globals
        self._markdown_styles = markdown_styles

        self.jinja_env.globals["resolve_template"] = self._resolve_component_template

        self.jinja_env.filters["md"] = self._markdown_filter

    @staticmethod
    def _markdown_filter(text: str) -> str:
        """一个将 Markdown 文本转换为 HTML 的 Jinja2 过滤器。"""
        if not isinstance(text, str):
            return ""
        return markdown.markdown(
            text,
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

    async def load_theme(self, theme_name: str = "default"):
        theme_dir = THEMES_PATH / theme_name
        if not theme_dir.is_dir():
            logger.error(f"主题 '{theme_name}' 不存在，将回退到默认主题。")
            if theme_name == "default":
                raise FileNotFoundError("默认主题 'default' 未找到！")
            theme_name = "default"
            theme_dir = THEMES_PATH / "default"

        if self.jinja_env.loader and isinstance(self.jinja_env.loader, ChoiceLoader):
            current_loaders = list(self.jinja_env.loader.loaders)
            if len(current_loaders) > 1:
                current_loaders[1] = FileSystemLoader(
                    [
                        str(theme_dir / "templates"),
                        str(THEMES_PATH / "default" / "templates"),
                    ]
                )
                self.jinja_env.loader = ChoiceLoader(current_loaders)
        else:
            logger.error("Jinja2 loader 不是 ChoiceLoader 或未设置，无法更新主题路径。")

        palette_path = theme_dir / "palette.json"
        palette = (
            json.loads(palette_path.read_text("utf-8")) if palette_path.exists() else {}
        )

        self.current_theme = Theme(
            name=theme_name,
            palette=palette,
            assets_dir=theme_dir / "assets",
            default_assets_dir=THEMES_PATH / "default" / "assets",
        )
        theme_context_dict = {
            "name": theme_name,
            "palette": palette,
            "assets_dir": theme_dir / "assets",
            "default_assets_dir": THEMES_PATH / "default" / "assets",
        }
        self.jinja_env.globals["theme"] = theme_context_dict
        logger.info(f"主题管理器已加载主题: {theme_name}")

    async def _resolve_component_template(self, component_path: str) -> str:
        """
        智能解析组件路径。
        如果路径是目录，则查找 manifest.json 以获取入口点。
        """
        if Path(component_path).suffix:
            return component_path

        manifest_path_str = f"{component_path}/manifest.json"

        if not self.jinja_env.loader:
            raise TemplateNotFound(
                f"Jinja2 loader 未配置。无法查找 '{manifest_path_str}'"
            )
        try:
            _, full_path, _ = self.jinja_env.loader.get_source(
                self.jinja_env, manifest_path_str
            )
            if full_path and Path(full_path).exists():
                async with aiofiles.open(full_path, encoding="utf-8") as f:
                    manifest_data = json.loads(await f.read())
                entrypoint = manifest_data.get("entrypoint")
                if not entrypoint:
                    raise RenderingError(
                        f"组件 '{component_path}' 的 manifest.json 中缺少 "
                        f"'entrypoint' 键。"
                    )
                return f"{component_path}/{entrypoint}"
        except TemplateNotFound:
            logger.debug(
                f"未找到 '{manifest_path_str}'，将回退到默认的 'main.html' 入口点。"
            )
            return f"{component_path}/main.html"
        raise TemplateNotFound(f"无法为组件 '{component_path}' 找到模板入口点。")

    async def get_template_manifest(
        self, component_path: str
    ) -> TemplateManifest | None:
        """
        查找并解析组件的 manifest.json 文件。
        """
        manifest_path_str = f"{component_path}/manifest.json"

        if not self.jinja_env.loader:
            return None

        try:
            _, full_path, _ = self.jinja_env.loader.get_source(
                self.jinja_env, manifest_path_str
            )
            if full_path and Path(full_path).exists():
                async with aiofiles.open(full_path, encoding="utf-8") as f:
                    manifest_data = json.loads(await f.read())
                return TemplateManifest(**manifest_data)
        except TemplateNotFound:
            return None
        return None

    def _resolve_markdown_style_path(self, style_name: str) -> Path | None:
        """
        按照 注册 -> 主题约定 -> 默认约定 的顺序解析 Markdown 样式路径。
        """
        if style_name in self._markdown_styles:
            logger.debug(f"找到已注册的 Markdown 样式: '{style_name}'")
            return self._markdown_styles[style_name]

        logger.warning(f"样式 '{style_name}' 在注册表中未找到。")
        return None

    async def _render_component_to_html(
        self,
        component: Renderable,
        required_scripts: list[str] | None = None,
        required_styles: list[str] | None = None,
        **kwargs,
    ) -> str:
        """将 Renderable 组件渲染成 HTML 字符串，并处理异步数据。"""
        if not self.current_theme:
            await self.load_theme()

        assert self.current_theme is not None, "主题加载失败"

        data_dict = component.get_render_data()

        custom_style_css = ""
        if hasattr(component, "get_extra_css"):
            css_result = component.get_extra_css(self)
            if inspect.isawaitable(css_result):
                custom_style_css = await css_result
            else:
                custom_style_css = css_result

        def asset_loader(asset_path: str) -> str:
            """[新增] 用于在Jinja2模板中解析静态资源的辅助函数。"""
            assert self.current_theme is not None
            current_theme_asset = self.current_theme.assets_dir / asset_path
            if current_theme_asset.exists():
                return current_theme_asset.relative_to(THEMES_PATH.parent).as_posix()

            default_theme_asset = self.current_theme.default_assets_dir / asset_path
            if default_theme_asset.exists():
                return default_theme_asset.relative_to(THEMES_PATH.parent).as_posix()

            logger.warning(
                f"资源文件在主题 '{self.current_theme.name}' 和 'default' 中均未找到: "
                f"{asset_path}"
            )
            return ""

        theme_context_dict = model_dump(self.current_theme)
        theme_context_dict["asset"] = asset_loader

        resolved_template_name = await self._resolve_component_template(
            str(component.template_name)
        )
        logger.debug(
            f"正在渲染组件 '{component.template_name}' "
            f"(主题: {self.current_theme.name})，解析模板: '{resolved_template_name}'",
            "RendererService",
        )
        if self._custom_filters:
            self.jinja_env.filters.update(self._custom_filters)
        if self._custom_globals:
            self.jinja_env.globals.update(self._custom_globals)
        template = self.jinja_env.get_template(resolved_template_name)

        template_context = {
            "data": data_dict,
            "theme": theme_context_dict,
            "theme_css": "",
            "custom_style_css": custom_style_css,
            "required_scripts": required_scripts or [],
            "required_styles": required_styles or [],
        }
        template_context.update(kwargs)

        return await template.render_async(**template_context)
