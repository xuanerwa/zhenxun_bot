from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession

from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.help_service import create_plugin_help_image
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.exception import EmptyError
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.rules import admin_check, ensure_group

__plugin_meta__ = PluginMetadata(
    name="群组管理员帮助",
    description="管理员帮助列表",
    usage="""
    管理员帮助
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.ADMIN,
        admin_level=1,
        introduction="""这是 群主/群管理 的帮助列表，里面记录了群组内开关功能的
        方法帮助以及群管特权方法，建议首次时在群组中发送 '管理员帮助' 查看""",
        precautions=[
            "只有群主/群管理 才能使用哦，群主拥有6级权限，管理员拥有5级权限！"
        ],
        configs=[],
    ).to_dict(),
)


async def build_html_help() -> bytes:
    """构建管理员帮助图片"""
    return await create_plugin_help_image(
        plugin_types=[PluginType.ADMIN, PluginType.SUPER_AND_ADMIN],
        page_title="群管理员帮助手册",
    )


_matcher = on_alconna(
    Alconna("管理员帮助"),
    rule=admin_check(1) & ensure_group,
    priority=5,
    block=True,
)


@_matcher.handle()
async def _(
    session: EventSession,
    arparma: Arparma,
):
    try:
        image_bytes = await build_html_help()
        await MessageUtils.build_message(image_bytes).send()
    except EmptyError:
        await MessageUtils.build_message("当前管理员帮助为空...").finish(reply_to=True)
    logger.info("查看管理员帮助", arparma.header_result, session=session)
