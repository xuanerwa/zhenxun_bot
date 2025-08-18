import asyncio
from collections.abc import Callable
import hashlib
from pathlib import Path
from typing import ClassVar, Literal

import aiofiles
from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
)
from nonebot.utils import is_coroutine_callable
import ujson as json

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import THEMES_PATH, UI_CACHE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.exception import RenderingError

from .engine import get_screenshot_engine
from .protocols import Renderable, RenderResult, ScreenshotEngine
from .theme import ThemeManager


class RendererService:
    """
    图片渲染服务的统一门面。

    负责编排和调用底层渲染服务，提供统一的渲染接口。
    支持多种渲染方式：组件渲染、模板渲染等。
    """

    _plugin_template_paths: ClassVar[dict[str, Path]] = {}

    def __init__(self):
        self._theme_manager: ThemeManager | None = None
        self._screenshot_engine: ScreenshotEngine | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._custom_filters: dict[str, Callable] = {}
        self._custom_globals: dict[str, Callable] = {}
        self._markdown_styles: dict[str, Path] = {}

    def register_template_namespace(self, namespace: str, path: Path):
        """[新增] 插件注册模板路径的入口点"""
        if namespace in self._plugin_template_paths:
            logger.warning(f"模板命名空间 '{namespace}' 已被注册，将被覆盖。")
        if not path.is_dir():
            raise ValueError(f"提供的路径 '{path}' 不是一个有效的目录。")
        self._plugin_template_paths[namespace] = path

    def register_markdown_style(self, name: str, path: Path):
        """
        为 Markdown 渲染器注册一个具名样式。
        """
        if name in self._markdown_styles:
            logger.warning(f"Markdown 样式 '{name}' 已被注册，将被覆盖。")
        if not path.is_file():
            raise ValueError(f"提供的路径 '{path}' 不是一个有效的 CSS 文件。")
        self._markdown_styles[name] = path
        logger.debug(f"已注册 Markdown 样式 '{name}' -> '{path}'")

    def filter(self, name: str) -> Callable:
        """
        装饰器：注册一个自定义 Jinja2 过滤器。
        """

        def decorator(func: Callable) -> Callable:
            if name in self._custom_filters:
                logger.warning(f"Jinja2 过滤器 '{name}' 已被注册，将被覆盖。")
            self._custom_filters[name] = func
            logger.debug(f"已注册自定义 Jinja2 过滤器: '{name}'")
            return func

        return decorator

    def global_function(self, name: str) -> Callable:
        """
        装饰器：注册一个自定义 Jinja2 全局函数。
        """

        def decorator(func: Callable) -> Callable:
            if name in self._custom_globals:
                logger.warning(f"Jinja2 全局函数 '{name}' 已被注册，将被覆盖。")
            self._custom_globals[name] = func
            logger.debug(f"已注册自定义 Jinja2 全局函数: '{name}'")
            return func

        return decorator

    async def initialize(self):
        """[新增] 延迟初始化方法，在 on_startup 钩子中调用"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return

            self._screenshot_engine = get_screenshot_engine()
            self._theme_manager = ThemeManager(
                self._plugin_template_paths,
                self._custom_filters,
                self._custom_globals,
                self._markdown_styles,
            )

            current_theme_name = Config.get_config("UI", "THEME", "default")
            await self._theme_manager.load_theme(current_theme_name)
            self._initialized = True

    async def _render_component(
        self, component: Renderable, use_cache: bool = False, **render_options
    ) -> RenderResult:
        """
        核心的私有渲染方法，执行完整的渲染流程。
        """
        cache_path = None
        if Config.get_config("UI", "CACHE") and use_cache:
            try:
                template_name = component.template_name
                data_dict = component.get_render_data()

                resolved_data_dict = {}
                for key, value in data_dict.items():
                    if is_coroutine_callable(value):  # type: ignore
                        resolved_data_dict[key] = await value
                    else:
                        resolved_data_dict[key] = value

                data_str = json.dumps(resolved_data_dict, sort_keys=True)

                cache_key_str = f"{template_name}:{data_str}"
                cache_filename = (
                    f"{hashlib.sha256(cache_key_str.encode()).hexdigest()}.png"
                )
                cache_path = UI_CACHE_PATH / cache_filename

                if cache_path.exists():
                    logger.debug(f"UI缓存命中: {cache_path}")
                    async with aiofiles.open(cache_path, "rb") as f:
                        image_bytes = await f.read()
                    return RenderResult(
                        image_bytes=image_bytes, html_content="<!-- from cache -->"
                    )
                logger.debug(f"UI缓存未命中: {cache_key_str[:100]}...")
            except Exception as e:
                logger.warning(f"UI缓存读取失败: {e}", e=e)
                cache_path = None

        try:
            if not self._initialized:
                await self.initialize()
            assert self._theme_manager is not None, "ThemeManager 未初始化"
            assert self._screenshot_engine is not None, "ScreenshotEngine 未初始化"

            if hasattr(component, "prepare"):
                await component.prepare()

            required_scripts = set(component.get_required_scripts())
            required_styles = set(component.get_required_styles())

            if hasattr(component, "required_scripts"):
                required_scripts.update(getattr(component, "required_scripts"))
            if hasattr(component, "required_styles"):
                required_styles.update(getattr(component, "required_styles"))

            data_dict = component.get_render_data()

            component_render_options = data_dict.get("render_options", {})
            if not isinstance(component_render_options, dict):
                component_render_options = {}

            manifest_options = {}
            if manifest := await self._theme_manager.get_template_manifest(
                component.template_name
            ):
                manifest_options = manifest.render_options or {}

            if (
                getattr(component, "_is_standalone_template", False)
                and hasattr(component, "template_path")
                and isinstance(
                    template_path := getattr(component, "template_path"), Path
                )
                and template_path.is_absolute()
            ):
                logger.debug(f"正在渲染独立模板: '{template_path}'", "RendererService")

                template_dir = template_path.parent
                temp_loader = FileSystemLoader(str(template_dir))
                temp_env = Environment(
                    loader=temp_loader,
                    enable_async=True,
                    autoescape=select_autoescape(["html", "xml"]),
                )

                temp_env.globals["theme"] = self._theme_manager.jinja_env.globals.get(
                    "theme", {}
                )
                temp_env.filters["md"] = self._theme_manager._markdown_filter

                template = temp_env.get_template(template_path.name)
                html_content = await template.render_async(data=data_dict)

                final_render_options = component_render_options.copy()
                final_render_options.update(render_options)

                image_bytes = await self._screenshot_engine.render(
                    html=html_content,
                    base_url_path=template_dir,
                    **final_render_options,
                )

                if Config.get_config("UI", "CACHE") and use_cache and cache_path:
                    try:
                        async with aiofiles.open(cache_path, "wb") as f:
                            await f.write(image_bytes)
                        logger.debug(f"UI缓存写入成功: {cache_path}")
                    except Exception as e:
                        logger.warning(f"UI缓存写入失败: {e}", e=e)

                return RenderResult(image_bytes=image_bytes, html_content=html_content)

            else:
                final_render_options = component_render_options.copy()
                final_render_options.update(manifest_options)
                final_render_options.update(render_options)

                if not self._theme_manager.current_theme:
                    raise RenderingError("渲染失败：主题未被正确加载。")

                html_content = await self._theme_manager._render_component_to_html(
                    component,
                    required_scripts=list(required_scripts),
                    required_styles=list(required_styles),
                    **final_render_options,
                )

                screenshot_options = final_render_options.copy()
                screenshot_options.pop("extra_css", None)
                screenshot_options.pop("frameless", None)

                image_bytes = await self._screenshot_engine.render(
                    html=html_content,
                    base_url_path=THEMES_PATH.parent,
                    **screenshot_options,
                )

                if Config.get_config("UI", "CACHE") and use_cache and cache_path:
                    try:
                        async with aiofiles.open(cache_path, "wb") as f:
                            await f.write(image_bytes)
                        logger.debug(f"UI缓存写入成功: {cache_path}")
                    except Exception as e:
                        logger.warning(f"UI缓存写入失败: {e}", e=e)

                return RenderResult(image_bytes=image_bytes, html_content=html_content)

        except Exception as e:
            logger.error(
                f"渲染组件 '{component.__class__.__name__}' 时发生错误",
                "RendererService",
                e=e,
            )
            raise RenderingError(
                f"渲染组件 '{component.__class__.__name__}' 失败"
            ) from e

    async def render(
        self,
        component: Renderable,
        use_cache: bool = False,
        debug_mode: Literal["none", "log"] = "none",
        **render_options,
    ) -> bytes:
        """
        统一的、多态的渲染入口，直接返回图片字节。

        参数:
            component: 一个 Renderable 实例 (如 RenderableComponent) 或一个
                      模板路径字符串。
            use_cache: (可选) 是否启用渲染缓存，默认为 False。
            **render_options: 传递给底层渲染引擎的额外参数。

        返回:
            bytes: 渲染后的图片数据。
        """
        result = await self._render_component(
            component,
            use_cache=use_cache,
            **render_options,
        )
        if debug_mode == "log" and result.html_content:
            logger.info(
                f"--- [UI DEBUG] HTML for {component.__class__.__name__} ---\n"
                f"{result.html_content}\n"
                f"--- [UI DEBUG] End of HTML ---"
            )
        if result.image_bytes is None:
            raise RenderingError("渲染成功但未能生成图片字节数据。")
        return result.image_bytes

    async def render_to_html(self, component: Renderable) -> str:
        """调试方法：只执行到HTML生成步骤。"""
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None, "ThemeManager 未初始化"

        return await self._theme_manager._render_component_to_html(component)

    async def reload_theme(self) -> str:
        """
        重新加载当前主题的配置和样式，并清除缓存的Jinja环境。
        """
        if not self._initialized:
            await self.initialize()
        assert self._theme_manager is not None, "ThemeManager 未初始化"

        current_theme_name = Config.get_config("UI", "THEME", "default")
        await self._theme_manager.load_theme(current_theme_name)
        logger.info(f"主题 '{current_theme_name}' 已成功重载。")
        return current_theme_name
