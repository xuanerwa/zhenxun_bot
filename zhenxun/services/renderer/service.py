import asyncio
from collections.abc import Callable, Generator
import hashlib
import json
from pathlib import Path

import aiofiles
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PrefixLoader
import markdown
from pydantic import BaseModel, ValidationError

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import THEMES_PATH, UI_CACHE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.exception import RenderingError

from .engines import BaseEngine, HtmlRenderer, MarkdownEngine
from .models import TemplateManifest, Theme

THEME_PATH = THEMES_PATH


class RendererService:
    """图片渲染服务管理器。"""

    def __init__(self):
        self._engines: dict[str, BaseEngine] = {
            "html": HtmlRenderer(),
            "markdown": MarkdownEngine(),
        }
        self._templates: dict[str, TemplateManifest] = {}
        self._template_paths: dict[str, Path] = {}
        self._plugin_template_paths: dict[str, Path] = {}
        self._plugin_manifests: dict[str, TemplateManifest] = {}
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._current_theme_data: Theme | None = None
        self._jinja_environments: dict[str, Environment] = {}

        self._custom_filters: dict[str, Callable] = {}
        self._custom_globals: dict[str, Callable] = {}
        self._markdown_styles: dict[str, Path] = {}

    def register_template_namespace(self, namespace: str, path: Path):
        """
        为插件注册一个模板命名空间。

        参数:
            namespace: 插件的唯一命名空间 (建议使用插件模块名)。
            path: 包含模板文件的目录路径。
        """
        if namespace in self._plugin_template_paths:
            logger.warning(f"模板命名空间 '{namespace}' 已被注册，将被覆盖。")
        if not path.is_dir():
            raise ValueError(f"提供的路径 '{path}' 不是一个有效的目录。")

        self._plugin_template_paths[namespace] = path
        logger.debug(f"已注册模板命名空间 '{namespace}' -> '{path}'")

    def register_markdown_style(self, name: str, path: Path):
        """
        [新增] 为 Markdown 渲染器注册一个具名样式。

        参数:
            name: 样式的唯一名称 (建议使用 '插件名:样式名' 格式以避免冲突)。
            path: 指向 CSS 文件的 Path 对象。
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

        参数:
            name: 过滤器在模板中的调用名称。为避免冲突，强烈建议使用
                '插件名_过滤器名' 的格式。
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

        参数:
            name: 函数在模板中的调用名称。为避免冲突，强烈建议使用
                '插件名_函数名' 的格式。
        """

        def decorator(func: Callable) -> Callable:
            if name in self._custom_globals:
                logger.warning(f"Jinja2 全局函数 '{name}' 已被注册，将被覆盖。")
            self._custom_globals[name] = func
            logger.debug(f"已注册自定义 Jinja2 全局函数: '{name}'")
            return func

        return decorator

    async def _load_theme(self, theme_name: str):
        """加载指定主题的配置和样式。"""
        theme_dir = THEME_PATH / theme_name
        if not theme_dir.is_dir():
            logger.error(f"主题 '{theme_name}' 不存在，将回退到默认主题。")
            if theme_name == "default":
                return
            theme_name = "default"
            theme_dir = THEME_PATH / "default"

        palette_path = theme_dir / "palette.json"
        default_palette_path = THEMES_PATH / "default" / "palette.json"

        palette = {}
        if palette_path.exists():
            try:
                palette = json.loads(palette_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning(f"主题 '{theme_name}' 的 palette.json 文件解析失败。")

        if not palette and default_palette_path.exists():
            logger.debug(
                f"主题 '{theme_name}' 未提供有效的 palette.json，"
                "回退到默认主题的调色板。"
            )
            try:
                palette = json.loads(default_palette_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.error("默认主题的 palette.json 文件解析失败，调色板将为空。")
                palette = {}
        elif not palette:
            logger.error("当前主题和默认主题均未找到有效的 palette.json。")

        self._current_theme_data = Theme(
            name=theme_name,
            palette=palette,
            style_css="",
            assets_dir=theme_dir / "assets",
            default_assets_dir=THEMES_PATH / "default" / "assets",
        )
        self._jinja_environments.clear()
        logger.info(f"渲染服务已加载主题: {theme_name}")

    async def reload_theme(self) -> str:
        """
        重新加载当前主题的配置和样式，并清除缓存的Jinja环境。
        """
        async with self._init_lock:
            current_theme_name = Config.get_config("UI", "THEME", "default")
            await self._load_theme(current_theme_name)
            logger.info(f"主题 '{current_theme_name}' 已成功重载。")
            return current_theme_name

    def _get_or_create_jinja_env(self, theme: Theme) -> Environment:
        """为指定主题获取或创建一个缓存的 Jinja2 环境。"""
        if theme.name in self._jinja_environments:
            return self._jinja_environments[theme.name]

        logger.debug(f"为主题 '{theme.name}' 创建新的 Jinja2 环境...")

        prefix_loader = PrefixLoader(
            {
                namespace: FileSystemLoader(str(path.absolute()))
                for namespace, path in self._plugin_template_paths.items()
            }
        )

        current_theme_templates_dir = THEMES_PATH / theme.name / "templates"
        default_theme_templates_dir = THEMES_PATH / "default" / "templates"
        theme_loader = FileSystemLoader(
            [
                str(current_theme_templates_dir.absolute()),
                str(default_theme_templates_dir.absolute()),
            ]
        )

        final_loader = ChoiceLoader([prefix_loader, theme_loader])

        env = Environment(
            loader=final_loader,
            enable_async=True,
            autoescape=True,
        )

        def markdown_filter(text: str) -> str:
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

        env.filters["md"] = markdown_filter

        if self._custom_filters:
            env.filters.update(self._custom_filters)
            logger.debug(
                f"向 Jinja2 环境注入了 {len(self._custom_filters)} 个自定义过滤器。"
            )
        if self._custom_globals:
            env.globals.update(self._custom_globals)
            logger.debug(
                f"向 Jinja2 环境注入了 {len(self._custom_globals)} 个自定义全局函数。"
            )

        self._jinja_environments[theme.name] = env
        return env

    async def initialize(self):
        """扫描并加载所有模板清单。"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return

            logger.info("开始扫描渲染模板...")
            base_template_path = THEMES_PATH / "default" / "templates"
            base_template_path.mkdir(exist_ok=True, parents=True)

            for manifest_path in base_template_path.glob("**/manifest.json"):
                template_dir = manifest_path.parent
                try:
                    manifest = TemplateManifest.parse_file(manifest_path)

                    template_name = template_dir.relative_to(
                        base_template_path
                    ).as_posix()

                    self._templates[template_name] = manifest
                    self._template_paths[template_name] = template_dir
                    logger.debug(
                        f"发现并加载基础模板 '{template_name}' "
                        f"(引擎: {manifest.engine})"
                    )
                except ValidationError as e:
                    logger.error(f"解析模板清单 '{manifest_path}' 失败: {e}")

            for namespace, plugin_template_path in self._plugin_template_paths.items():
                for manifest_path in plugin_template_path.glob("**/manifest.json"):
                    template_dir = manifest_path.parent
                    try:
                        manifest = TemplateManifest.parse_file(manifest_path)

                        relative_path = template_dir.relative_to(
                            plugin_template_path
                        ).as_posix()
                        template_name_with_ns = f"{namespace}:{relative_path}"

                        self._plugin_manifests[template_name_with_ns] = manifest
                        logger.debug(
                            f"发现并加载插件模板 '{template_name_with_ns}' "
                            f"(引擎: {manifest.engine})"
                        )
                    except ValidationError as e:
                        logger.error(f"解析插件模板清单 '{manifest_path}' 失败: {e}")

            current_theme_name = Config.get_config("UI", "THEME", "default")
            await self._load_theme(current_theme_name)

            self._initialized = True
            logger.info(
                f"渲染模板扫描完成，共加载 {len(self._templates)} 个基础模板和 "
                f"{len(self._plugin_manifests)} 个插件模板。"
            )

    def _yield_theme_paths(self, relative_path: Path) -> Generator[Path, None, None]:
        """
        按优先级生成一个资源的完整路径（当前主题 -> 默认主题）。
        """
        if not self._current_theme_data:
            return

        current_theme_path = THEMES_PATH / self._current_theme_data.name / relative_path
        yield current_theme_path

        if self._current_theme_data.name != "default":
            default_theme_path = THEMES_PATH / "default" / relative_path
            yield default_theme_path

    def _resolve_markdown_style_path(self, style_name: str) -> Path | None:
        """
        按照 注册 -> 主题约定 -> 默认约定 的顺序解析 Markdown 样式路径。
        """
        if style_name in self._markdown_styles:
            logger.debug(f"找到已注册的 Markdown 样式: '{style_name}'")
            return self._markdown_styles[style_name]

        conventional_relative_paths = [
            Path("templates")
            / "components"
            / "cards"
            / "markdown_image"
            / "styles"
            / f"{style_name}.css",
            Path("assets") / "css" / "markdown" / f"{style_name}.css",
        ]

        for relative_path in conventional_relative_paths:
            for potential_path in self._yield_theme_paths(relative_path):
                if potential_path.exists():
                    logger.debug(f"在约定路径找到 Markdown 样式: {potential_path}")
                    return potential_path

        logger.warning(f"样式 '{style_name}' 在注册表和约定路径中均未找到。")
        return None

    def _resolve_style_path(self, template_name: str, style_name: str) -> Path | None:
        """
        [重构后] 实现 当前主题 -> 默认主题 的回退查找逻辑
        """
        relative_style_path = (
            Path("templates") / template_name / "styles" / f"{style_name}.css"
        )

        for potential_path in self._yield_theme_paths(relative_style_path):
            if potential_path.exists():
                logger.debug(f"找到样式 '{style_name}': {potential_path}")
                return potential_path

        logger.warning(f"样式 '{style_name}' 在当前主题和默认主题中均未找到。")
        return None

    async def render(
        self,
        template_name: str,
        data: dict | BaseModel | None = None,
        use_cache: bool = False,
        style_name: str | None = None,
        **render_options_override,
    ) -> bytes:
        """
        渲染指定的模板，并支持透明缓存。
        """
        await self.initialize()

        try:
            extra_css_paths = []
            custom_markdown_css_path = None
            manifest: TemplateManifest | None = self._templates.get(
                template_name
            ) or self._plugin_manifests.get(template_name)

            if style_name:
                if manifest and manifest.engine == "markdown":
                    custom_markdown_css_path = self._resolve_markdown_style_path(
                        style_name
                    )
                else:
                    resolved_path = self._resolve_style_path(template_name, style_name)
                    if resolved_path:
                        extra_css_paths.append(resolved_path)

            cache_path = None
            if Config.get_config("UI", "CACHE") and use_cache:
                try:
                    if isinstance(data, BaseModel):
                        data_str = f"{data.__class__.__name__}:{data!s}"
                    else:
                        data_str = json.dumps(data or {}, sort_keys=True)
                    cache_key_str = f"{template_name}:{data_str}"
                    cache_filename = (
                        f"{hashlib.sha256(cache_key_str.encode()).hexdigest()}.png"
                    )
                    cache_path = UI_CACHE_PATH / cache_filename

                    if cache_path.exists():
                        logger.debug(f"UI缓存命中: {cache_path}")
                        async with aiofiles.open(cache_path, "rb") as f:
                            return await f.read()
                    logger.debug(f"UI缓存未命中: {cache_key_str[:100]}...")
                except Exception as e:
                    logger.warning(f"UI缓存读取失败: {e}", e=e)
                    cache_path = None

            if not self._current_theme_data:
                raise RuntimeError("主题未被正确加载，无法进行渲染。")

            manifest: TemplateManifest | None = None
            final_template_dir: Path | None = None
            relative_template_name: str = ""
            is_plugin_template = ":" in template_name

            if is_plugin_template:
                namespace, path_part = template_name.split(":", 1)
                manifest = self._plugin_manifests.get(template_name)
                if namespace in self._plugin_template_paths:
                    plugin_base_path = self._plugin_template_paths[namespace]
                    final_template_dir = plugin_base_path / Path(path_part).parent

                relative_template_name = template_name
                if manifest:
                    logger.debug(f"使用插件模板: '{template_name}'")

            else:
                theme_template_dir = (
                    THEMES_PATH
                    / self._current_theme_data.name
                    / "templates"
                    / template_name
                )
                default_template_dir = (
                    THEMES_PATH / "default" / "templates" / template_name
                )

                if (
                    theme_template_dir.is_dir()
                    and (theme_template_dir / "manifest.json").is_file()
                ):
                    final_template_dir = theme_template_dir
                    logger.debug(
                        f"使用主题 '{self._current_theme_data.name}' "
                        f"覆盖的模板: '{template_name}'"
                    )
                elif (
                    default_template_dir.is_dir()
                    and (default_template_dir / "manifest.json").is_file()
                ):
                    final_template_dir = default_template_dir
                    logger.debug(f"使用基础(default)模板: '{template_name}'")

                if final_template_dir:
                    try:
                        manifest = TemplateManifest.parse_file(
                            final_template_dir / "manifest.json"
                        )
                        relative_template_name = (
                            Path(template_name) / manifest.entrypoint
                        ).as_posix()
                    except (ValidationError, FileNotFoundError) as e:
                        logger.error(f"无法加载模板 '{template_name}' 的清单文件: {e}")
                        manifest = None

            if not manifest or not final_template_dir:
                raise ValueError(f"模板 '{template_name}' 未找到或清单文件加载失败。")

            engine_name = manifest.engine
            engine = self._engines.get(engine_name)
            if not engine:
                raise ValueError(f"未找到名为 '{engine_name}' 的渲染引擎。")
            jinja_environment = self._get_or_create_jinja_env(self._current_theme_data)

            final_render_options = manifest.render_options.copy()
            final_render_options.update(render_options_override)

            image_bytes = await engine.render(
                template_name=relative_template_name,
                data=data,
                theme=self._current_theme_data,
                jinja_env=jinja_environment,
                extra_css_paths=extra_css_paths,
                custom_css_path=custom_markdown_css_path,
                **final_render_options,
            )

            if Config.get_config("UI", "CACHE") and use_cache and cache_path:
                try:
                    async with aiofiles.open(cache_path, "wb") as f:
                        await f.write(image_bytes)
                    logger.debug(f"UI缓存写入成功: {cache_path}")
                except Exception as e:
                    logger.warning(f"UI缓存写入失败: {e}", e=e)

            return image_bytes

        except Exception as e:
            logger.error(
                f"渲染模板 '{template_name}' 时发生错误", "RendererService", e=e
            )
            raise RenderingError(f"渲染模板 '{template_name}' 失败") from e
