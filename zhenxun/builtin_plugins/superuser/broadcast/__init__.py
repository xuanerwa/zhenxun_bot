from arclet.alconna import AllParam
from nepattern import UnionPattern
from nonebot.adapters import Bot, Event
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
import nonebot_plugin_alconna as alc
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg.segment import (
    At,
    AtAll,
    Audio,
    Button,
    Emoji,
    File,
    Hyper,
    Image,
    Keyboard,
    Reference,
    Reply,
    Text,
    Video,
    Voice,
)
from nonebot_plugin_session import EventSession

from zhenxun.configs.utils import PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from .broadcast_manager import BroadcastManager
from .message_processor import (
    _extract_broadcast_content,
    get_broadcast_target_groups,
    send_broadcast_and_notify,
)

BROADCAST_SEND_DELAY_RANGE = (1, 3)

__plugin_meta__ = PluginMetadata(
    name="广播",
    description="昭告天下！",
    usage="""
    向所有群组或指定标签的群组发送广播消息。

**基础用法**
- `广播 [消息内容]`：向所有群组发送广播。
- `广播` (并引用一条消息)：将引用的消息作为内容进行广播。

**高级定向广播**
- `广播 -t <标签名> [消息内容]`：向指定标签下的所有群组广播。
- `广播到 <标签名> [消息内容]`：与 `-t` 等效的快捷方式。

**标签可以是静态的，也可以是动态的，例如：**
- `广播到 核心群 通知：...`
- `广播到 成员数>500的群 通知：...`

**其他命令**
- `广播撤回` (别名: `recall`)：撤回最近一次发送的广播。

特性：
- 在群组中使用广播时，不会将消息发送到当前群组
- 在私聊中使用广播时，会发送到所有群组

别名：
- bc (广播的简写)
- recall (广播撤回的别名)
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="1.3",
        plugin_type=PluginType.SUPERUSER,
        configs=[
            RegisterConfig(
                module="_task",
                key="DEFAULT_BROADCAST",
                value=True,
                help="被动 广播 进群默认开关状态",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="_task",
                key="BROADCAST_CONCURRENCY_LIMIT",
                value=10,
                help="广播时的最大并发任务数，以避免API速率限制",
                default_value=10,
            ),
        ],
        tasks=[Task(module="broadcast", name="广播")],
    ).to_dict(),
)

AnySeg = (
    UnionPattern(
        [
            Text,
            Image,
            At,
            AtAll,
            Audio,
            Video,
            File,
            Emoji,
            Reply,
            Reference,
            Hyper,
            Button,
            Keyboard,
            Voice,
        ]
    )
    @ "AnySeg"
)

_matcher = on_alconna(
    Alconna(
        "广播",
        Args["content?", AllParam],
        alc.Option(
            "-t|--tag", Args["tag_name_bc", str], help_text="向指定标签的群组广播"
        ),
    ),
    aliases={"bc"},
    priority=1,
    permission=SUPERUSER,
    block=True,
    rule=to_me(),
    use_origin=False,
)

_matcher.shortcut("广播到 {tag}", command="广播 -t {tag} {%*}")

_recall_matcher = on_alconna(
    Alconna("广播撤回"),
    aliases={"recall"},
    priority=1,
    permission=SUPERUSER,
    block=True,
    rule=to_me(),
)


@_matcher.handle()
async def handle_broadcast(
    bot: Bot,
    event: Event,
    session: EventSession,
    arp: alc.Arparma,
    tag_name_match: alc.Match[str] = alc.AlconnaMatch("tag_name_bc"),
):
    broadcast_content_msg = await _extract_broadcast_content(bot, event, arp, session)
    if not broadcast_content_msg:
        return

    tag_name_to_broadcast = None
    force_send = False

    if tag_name_match.available:
        tag_name_to_broadcast = tag_name_match.result
        force_send = True

    mode_desc = "强制发送到标签" if force_send else "普通发送"
    logger.debug(
        f"广播模式: {mode_desc}, 标签名: {tag_name_to_broadcast}",
        "广播",
    )

    target_groups_console, groups_to_actually_send = await get_broadcast_target_groups(
        bot, session, tag_name_to_broadcast, force_send
    )

    if not target_groups_console:
        if tag_name_to_broadcast:
            await MessageUtils.build_message(
                f"标签 '{tag_name_to_broadcast}' 中没有群组或标签不存在。"
            ).send(reply_to=True)
        return

    if not groups_to_actually_send:
        if not force_send and target_groups_console:
            await MessageUtils.build_message(
                "没有启用了广播功能的目标群组可供立即发送。"
            ).send(reply_to=True)
        return

    try:
        await send_broadcast_and_notify(
            bot,
            event,
            broadcast_content_msg,
            groups_to_actually_send,
            target_groups_console,
            session,
            force_send,
        )
    except Exception as e:
        error_msg = "发送广播失败"
        BroadcastManager.log_error(error_msg, e, session)
        await bot.send_private_msg(
            user_id=str(event.get_user_id()), message=f"{error_msg}。"
        )


@_recall_matcher.handle()
async def handle_broadcast_recall(
    bot: Bot,
    event: Event,
    session: EventSession,
):
    """处理广播撤回命令"""
    await MessageUtils.build_message("正在尝试撤回最近一次广播...").send()

    try:
        success_count, error_count = await BroadcastManager.recall_last_broadcast(
            bot, session
        )

        user_id = str(event.get_user_id())
        if success_count == 0 and error_count == 0:
            await bot.send_private_msg(
                user_id=user_id,
                message="没有找到最近的广播消息记录，可能已经撤回或超过可撤回时间。",
            )
        else:
            result = f"广播撤回完成!\n成功撤回 {success_count} 条消息"
            if error_count:
                result += f"\n撤回失败 {error_count} 条消息 (可能已过期或无权限)"
            await bot.send_private_msg(user_id=user_id, message=result)
            BroadcastManager.log_info(
                f"广播撤回完成: 成功 {success_count}, 失败 {error_count}", session
            )
    except Exception as e:
        error_msg = "撤回广播消息失败"
        BroadcastManager.log_error(error_msg, e, session)
        await bot.send_private_msg(
            user_id=str(event.get_user_id()), message=f"{error_msg}。"
        )
