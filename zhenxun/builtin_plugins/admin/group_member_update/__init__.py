import asyncio
import random

import nonebot
from nonebot import on_notice
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupIncreaseNoticeEvent
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import BotConfig
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.services.tags import tag_manager
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.rules import admin_check, ensure_group, notice_rule

from ._data_source import MemberUpdateManage

__plugin_meta__ = PluginMetadata(
    name="更新群组成员列表",
    description="更新群组成员列表",
    usage="""
    更新群组成员的基本信息
    指令：
        更新群组成员信息
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=1,
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("更新群组成员信息"),
    rule=admin_check(1) & ensure_group,
    priority=5,
    block=True,
)


_notice = on_notice(priority=1, block=False, rule=notice_rule(GroupIncreaseNoticeEvent))


_update_all_matcher = on_alconna(
    Alconna("更新所有群组信息"),
    permission=SUPERUSER,
    priority=1,
    block=True,
)


async def _update_all_groups_task(bot: Bot, session: EventSession):
    """
    在后台执行所有群组的更新任务，并向超级用户发送最终报告。
    """
    success_count = 0
    fail_count = 0
    total_count = 0
    bot_id = bot.self_id

    logger.info(f"Bot {bot_id}: 开始执行所有群组信息更新任务...", "更新所有群组")
    try:
        group_list, _ = await PlatformUtils.get_group_list(bot)
        total_count = len(group_list)
        for i, group in enumerate(group_list):
            try:
                logger.debug(
                    f"Bot {bot_id}: 正在更新第 {i + 1}/{total_count} 个群组: "
                    f"{group.group_id}",
                    "更新所有群组",
                )
                await MemberUpdateManage.update_group_member(bot, group.group_id)
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"Bot {bot_id}: 更新群组 {group.group_id} 信息失败",
                    "更新所有群组",
                    e=e,
                )
            await asyncio.sleep(random.uniform(1.5, 3.0))
    except Exception as e:
        logger.error(f"Bot {bot_id}: 获取群组列表失败，任务中断", "更新所有群组", e=e)
        await PlatformUtils.send_superuser(
            bot,
            f"Bot {bot_id} 更新所有群组信息任务失败：无法获取群组列表。",
            session.id1,
        )
        return

    await tag_manager._invalidate_cache()
    summary_message = (
        f"🤖 Bot {bot_id} 所有群组信息更新任务完成！\n"
        f"总计群组: {total_count}\n"
        f"✅ 成功: {success_count}\n"
        f"❌ 失败: {fail_count}"
    )
    logger.info(summary_message.replace("\n", " | "), "更新所有群组")
    await PlatformUtils.send_superuser(bot, summary_message, session.id1)


@_update_all_matcher.handle()
async def _(bot: Bot, session: EventSession):
    await MessageUtils.build_message(
        "已开始在后台更新所有群组信息，过程可能需要几分钟到几十分钟，完成后将私聊通知您。"
    ).send(reply_to=True)
    asyncio.create_task(_update_all_groups_task(bot, session))  # noqa: RUF006


@_matcher.handle()
async def _(bot: Bot, session: EventSession, arparma: Arparma):
    if gid := session.id3 or session.id2:
        logger.info("更新群组成员信息", arparma.header_result, session=session)
        result = await MemberUpdateManage.update_group_member(bot, gid)
        await MessageUtils.build_message(result).finish(reply_to=True)
        await tag_manager._invalidate_cache()
    await MessageUtils.build_message("群组id为空...").send()


@_notice.handle()
async def _(bot: Bot, event: GroupIncreaseNoticeEvent):
    if str(event.user_id) == bot.self_id:
        await MemberUpdateManage.update_group_member(bot, str(event.group_id))
        logger.info(
            f"{BotConfig.self_nickname}加入群聊更新群组信息",
            "更新群组成员列表",
            session=event.user_id,
            group_id=event.group_id,
        )
        await tag_manager._invalidate_cache()


@scheduler.scheduled_job(
    "interval",
    minutes=5,
)
async def _():
    for bot in nonebot.get_bots().values():
        if PlatformUtils.get_platform(bot) == "qq":
            try:
                group_list, _ = await PlatformUtils.get_group_list(bot)
                if group_list:
                    for group in group_list:
                        try:
                            await MemberUpdateManage.update_group_member(
                                bot, group.group_id
                            )
                            logger.debug("自动更新群组成员信息成功...")
                        except Exception as e:
                            logger.error(
                                f"Bot: {bot.self_id} 自动更新群组成员信息失败",
                                target=group.group_id,
                                e=e,
                            )
            except Exception as e:
                logger.error(f"Bot: {bot.self_id} 自动更新群组信息", e=e)
        logger.debug(f"自动 Bot: {bot.self_id} 更新群组成员信息成功...")

    await tag_manager._invalidate_cache()
