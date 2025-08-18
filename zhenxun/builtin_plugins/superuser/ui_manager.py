from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna

from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.services import renderer_service
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="UI管理",
    description="管理UI、主题和渲染服务的相关配置",
    usage="""
    指令：
        重载UI主题
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
        configs=[
            RegisterConfig(
                module="UI",
                key="THEME",
                value="default",
                help="设置渲染服务使用的全局主题名称(对应 resources/themes/下的目录名)",
                default_value="default",
                type=str,
            ),
            RegisterConfig(
                module="UI",
                key="CACHE",
                value=True,
                help="是否为渲染服务生成的图片启用文件缓存",
                default_value=True,
                type=bool,
            ),
        ],
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("重载主题"),
    rule=to_me(),
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@_matcher.handle()
async def _(arparma: Arparma):
    theme_name = await renderer_service.reload_theme()
    logger.info(
        f"UI主题已重载为: {theme_name}", "UI管理器", session=arparma.header_result
    )
    await MessageUtils.build_message(f"UI主题已成功重载为 '{theme_name}'！").send(
        reply_to=True
    )
