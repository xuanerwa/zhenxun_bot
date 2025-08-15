from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.help_service import create_plugin_help_image
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.exception import EmptyError
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="超级用户帮助",
    description="超级用户帮助",
    usage="""
    超级用户帮助
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)


async def build_html_help() -> bytes:
    """构建超级用户帮助图片"""
    return await create_plugin_help_image(
        plugin_types=[PluginType.SUPERUSER, PluginType.SUPER_AND_ADMIN],
        page_title="超级用户帮助手册",
    )


_matcher = on_alconna(
    Alconna("超级用户帮助"),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    try:
        image_bytes = await build_html_help()
        await MessageUtils.build_message(image_bytes).send()
    except EmptyError:
        await MessageUtils.build_message("当前超级用户帮助为空...").finish(
            reply_to=True
        )
    logger.info("查看超级用户帮助", arparma.header_result, session=session)
