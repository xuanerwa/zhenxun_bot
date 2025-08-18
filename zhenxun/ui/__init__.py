from pathlib import Path
from typing import Any, Literal

from zhenxun.services.renderer.protocols import Renderable

from .builders.core.layout import LayoutBuilder
from .models.core.base import RenderableComponent
from .models.core.markdown import MarkdownData
from .models.core.template import TemplateComponent


def template(path: str | Path, data: dict[str, Any]) -> TemplateComponent:
    """
    创建一个基于独立模板文件的UI组件。
    """
    if isinstance(path, str):
        path = Path(path)

    return TemplateComponent(template_path=path, data=data)


def markdown(content: str, style: str | Path | None = "default") -> MarkdownData:
    """
    创建一个基于Markdown内容的UI组件。
    """
    if isinstance(style, Path):
        return MarkdownData(markdown=content, css_path=str(style.absolute()))
    return MarkdownData(markdown=content, style_name=style)


def vstack(children: list[RenderableComponent], **layout_options) -> "LayoutBuilder":
    """
    创建一个垂直布局组件。
    """
    builder = LayoutBuilder.column(**layout_options)
    for child in children:
        builder.add_item(child)
    return builder


def hstack(children: list[RenderableComponent], **layout_options) -> "LayoutBuilder":
    """
    创建一个水平布局组件。
    """
    builder = LayoutBuilder.row(**layout_options)
    for child in children:
        builder.add_item(child)
    return builder


async def render(
    component_or_path: Renderable | str | Path,
    data: dict | None = None,
    *,
    use_cache: bool = False,
    debug_mode: Literal["none", "log"] = "none",
    **kwargs,
) -> bytes:
    """
    统一的UI渲染入口。

    用法:
    1. 渲染一个已构建的UI组件: `render(my_builder.build())`
    2. 直接渲染一个模板文件: `render("path/to/template", data={...})`
    """
    from zhenxun.services import renderer_service

    component: Renderable
    if isinstance(component_or_path, str | Path):
        if data is None:
            raise ValueError("使用模板路径渲染时必须提供 'data' 参数。")
        component = TemplateComponent(template_path=component_or_path, data=data)
    else:
        component = component_or_path

    return await renderer_service.render(
        component, use_cache=use_cache, debug_mode=debug_mode, **kwargs
    )


async def render_template(
    path: str | Path, data: dict, use_cache: bool = False, **kwargs
) -> bytes:
    """
    渲染一个独立的Jinja2模板文件。

    这是一个便捷函数，封装了 render() 函数的调用，提供更简洁的模板渲染接口。

    参数:
        path: 模板文件路径，相对于主题模板目录。
        data: 传递给模板的数据字典。
        use_cache: (可选) 是否启用渲染缓存，默认为 False。
        **kwargs: 传递给渲染服务的额外参数。

    返回:
        bytes: 渲染后的图片数据。
    """
    return await render(path, data, use_cache=use_cache, **kwargs)


async def render_markdown(
    md: str, style: str | Path | None = "default", use_cache: bool = False, **kwargs
) -> bytes:
    """
    将Markdown字符串渲染为图片。

    这是一个便捷函数，封装了 render() 函数的调用，专门用于渲染Markdown内容。

    参数:
        md: 要渲染的Markdown内容字符串。
        style: (可选) 样式名称或自定义CSS文件路径，默认为 "default"。
        use_cache: (可选) 是否启用渲染缓存，默认为 False。
        **kwargs: 传递给渲染服务的额外参数。

    返回:
        bytes: 渲染后的图片数据。
    """
    component: MarkdownData
    if isinstance(style, Path):
        component = MarkdownData(markdown=md, css_path=str(style.absolute()))
    else:
        component = MarkdownData(markdown=md, style_name=style)

    return await render(component, use_cache=use_cache, **kwargs)


from zhenxun.services.renderer.protocols import RenderResult


async def render_full_result(
    component: Renderable, use_cache: bool = False, **kwargs
) -> RenderResult:
    """
    渲染组件并返回包含图片和HTML的完整结果对象，用于调试和高级用途。
    """
    from zhenxun.services import renderer_service

    return await renderer_service._render_component(
        component, use_cache=use_cache, **kwargs
    )
