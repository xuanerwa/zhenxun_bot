"""
图片渲染服务

提供一个统一的、可扩展的接口来将结构化数据渲染成图片。
"""

from zhenxun.configs.config import Config
from zhenxun.utils.manager.priority_manager import PriorityLifecycle

from .service import RendererService

Config.add_plugin_config(
    "UI",
    "THEME",
    "default",
    help="设置渲染服务使用的全局主题名称 (对应 resources/themes/下的目录名)",
    default_value="default",
    type=str,
)
Config.add_plugin_config(
    "UI",
    "CACHE",
    True,
    help="是否为渲染服务生成的图片启用文件缓存",
    default_value=True,
    type=bool,
)

renderer_service = RendererService()


@PriorityLifecycle.on_startup(priority=10)
async def _init_renderer_service():
    """在Bot启动时预热渲染服务，扫描并加载所有模板。"""
    await renderer_service.initialize()


__all__ = ["renderer_service"]
