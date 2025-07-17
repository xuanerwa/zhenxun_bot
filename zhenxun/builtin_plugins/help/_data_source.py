from pathlib import Path

import nonebot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_htmlrender import template_to_pic
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import IMAGE_PATH, TEMPLATE_PATH
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.level_user import LevelUser
from zhenxun.models.plugin_info import PluginInfo
from zhenxun.models.statistics import Statistics
from zhenxun.services import (
    LLMException,
    LLMMessage,
    generate,
)
from zhenxun.services.log import logger
from zhenxun.utils._image_template import Markdown
from zhenxun.utils.enum import PluginType
from zhenxun.utils.image_utils import BuildImage, ImageTemplate

from ._config import (
    GROUP_HELP_PATH,
    SIMPLE_DETAIL_HELP_IMAGE,
    SIMPLE_HELP_IMAGE,
    base_config,
)
from .html_help import build_html_image
from .normal_help import build_normal_image
from .zhenxun_help import build_zhenxun_image

random_bk_path = IMAGE_PATH / "background" / "help" / "simple_help"

background = IMAGE_PATH / "background" / "0.png"


driver = nonebot.get_driver()


async def create_help_img(
    session: Uninfo, group_id: str | None, is_detail: bool
) -> Path:
    """生成帮助图片

    参数:
        session: Uninfo
        group_id: 群号
    """
    help_type = base_config.get("type", "").strip().lower()

    match help_type:
        case "html":
            result = BuildImage.open(
                await build_html_image(session, group_id, is_detail)
            )
        case "zhenxun":
            result = BuildImage.open(
                await build_zhenxun_image(session, group_id, is_detail)
            )
        case _:
            result = await build_normal_image(group_id, is_detail)
    if group_id:
        save_path = GROUP_HELP_PATH / f"{group_id}_{is_detail}.png"
    elif is_detail:
        save_path = SIMPLE_DETAIL_HELP_IMAGE
    else:
        save_path = SIMPLE_HELP_IMAGE
    await result.save(save_path)
    return save_path


async def get_user_allow_help(user_id: str) -> list[PluginType]:
    """获取用户可访问插件类型列表

    参数:
        user_id: 用户id

    返回:
        list[PluginType]: 插件类型列表
    """
    type_list = [PluginType.NORMAL, PluginType.DEPENDANT]
    for level in await LevelUser.filter(user_id=user_id).values_list(
        "user_level", flat=True
    ):
        if level > 0:  # type: ignore
            type_list.extend((PluginType.ADMIN, PluginType.SUPER_AND_ADMIN))
            break
    if user_id in driver.config.superusers:
        type_list.append(PluginType.SUPERUSER)
    return type_list


async def get_normal_help(
    metadata: PluginMetadata, extra: PluginExtraData, is_superuser: bool
) -> str | bytes:
    """构建默认帮助详情

    参数:
        metadata: PluginMetadata
        extra: PluginExtraData
        is_superuser: 是否超级用户帮助

    返回:
        str | bytes: 返回信息
    """
    items = None
    if is_superuser:
        if usage := extra.superuser_help:
            items = {
                "简介": metadata.description,
                "用法": usage,
            }
    else:
        items = {
            "简介": metadata.description,
            "用法": metadata.usage,
        }
    if items:
        return (await ImageTemplate.hl_page(metadata.name, items)).pic2bytes()
    return "该功能没有帮助信息"


def min_leading_spaces(str_list: list[str]) -> int:
    min_spaces = 9999

    for s in str_list:
        leading_spaces = len(s) - len(s.lstrip(" "))

        if leading_spaces < min_spaces:
            min_spaces = leading_spaces

    return min_spaces if min_spaces != 9999 else 0


def split_text(text: str):
    split_text = text.split("\n")
    min_spaces = min_leading_spaces(split_text)
    if min_spaces > 0:
        split_text = [s[min_spaces:] for s in split_text]
    return [s.replace(" ", "&nbsp;") for s in split_text]


async def get_zhenxun_help(
    module: str, metadata: PluginMetadata, extra: PluginExtraData, is_superuser: bool
) -> str | bytes:
    """构建ZhenXun帮助详情

    参数:
        module: 模块名
        metadata: PluginMetadata
        extra: PluginExtraData
        is_superuser: 是否超级用户帮助

    返回:
        str | bytes: 返回信息
    """
    call_count = await Statistics.filter(plugin_name=module).count()
    usage = metadata.usage
    if is_superuser:
        if not extra.superuser_help:
            return "该功能没有超级用户帮助信息"
        usage = extra.superuser_help
    return await template_to_pic(
        template_path=str((TEMPLATE_PATH / "help_detail").absolute()),
        template_name="main.html",
        templates={
            "title": metadata.name,
            "author": extra.author,
            "version": extra.version,
            "call_count": call_count,
            "descriptions": split_text(metadata.description),
            "usages": split_text(usage),
        },
        pages={
            "viewport": {"width": 824, "height": 590},
            "base_url": f"file://{TEMPLATE_PATH}",
        },
        wait=2,
    )


async def get_plugin_help(user_id: str, name: str, is_superuser: bool) -> str | bytes:
    """获取功能的帮助信息

    参数:
        user_id: 用户id
        name: 插件名称或id
        is_superuser: 是否为超级用户
    """
    type_list = await get_user_allow_help(user_id)
    if name.isdigit():
        plugin = await PluginInfo.get_or_none(id=int(name), plugin_type__in=type_list)
    else:
        plugin = await PluginInfo.get_or_none(
            name__iexact=name, load_status=True, plugin_type__in=type_list
        )
    if plugin:
        _plugin = nonebot.get_plugin_by_module_name(plugin.module_path)
        if _plugin and _plugin.metadata:
            extra_data = PluginExtraData(**_plugin.metadata.extra)
            if Config.get_config("help", "detail_type") == "zhenxun":
                return await get_zhenxun_help(
                    plugin.module, _plugin.metadata, extra_data, is_superuser
                )
            else:
                return await get_normal_help(_plugin.metadata, extra_data, is_superuser)
        return "糟糕! 该功能没有帮助喔..."
    return "没有查找到这个功能噢..."


async def get_llm_help(question: str, user_id: str) -> str | bytes:
    """
    使用LLM来回答用户的自然语言求助。

    参数:
        question: 用户的问题。
        user_id: 提问用户的ID。

    返回:
        str | bytes: LLM生成的回答或错误提示。
    """

    try:
        allowed_types = await get_user_allow_help(user_id)

        plugins = await PluginInfo.filter(
            is_show=True, plugin_type__in=allowed_types
        ).all()

        knowledge_base_parts = []
        for p in plugins:
            meta = nonebot.get_plugin_by_module_name(p.module_path)
            if not meta or not meta.metadata:
                continue
            usage = meta.metadata.usage.strip() or "无"
            desc = meta.metadata.description.strip() or "无"
            part = f"功能名称: {p.name}\n功能描述: {desc}\n用法示例:\n{usage}"
            knowledge_base_parts.append(part)

        if not knowledge_base_parts:
            return "抱歉，根据您的权限，当前没有可供查询的功能信息。"

        knowledge_base = "\n\n---\n\n".join(knowledge_base_parts)

        user_role = "普通用户"
        if PluginType.SUPERUSER in allowed_types:
            user_role = "超级管理员"
        elif PluginType.ADMIN in allowed_types:
            user_role = "管理员"

        base_system_prompt = (
            f"你是一个精通机器人功能的AI助手。当前向你提问的用户是一位「{user_role}」。\n"
            "你的任务是根据下面提供的功能列表和详细说明，来回答用户关于如何使用机器人的问题。\n"
            "请仔细阅读每个功能的描述和用法，然后用简洁、清晰的语言告诉用户应该使用哪个或哪些命令来解决他们的问题。\n"
            "如果找不到完全匹配的功能，可以推荐最相关的一个或几个。直接给出操作指令和简要解释即可。"
        )

        if (
            Config.get_config("help", "LLM_HELPER_STYLE")
            and Config.get_config("help", "LLM_HELPER_STYLE").strip()
        ):
            style = Config.get_config("help", "LLM_HELPER_STYLE")
            style_instruction = f"请务必使用「{style}」的风格和口吻来回答。"
            system_prompt = f"{base_system_prompt}\n{style_instruction}"
        else:
            system_prompt = base_system_prompt

        full_instruction = (
            f"{system_prompt}\n\n=== 功能列表和说明 ===\n{knowledge_base}"
        )

        messages = [
            LLMMessage.system(full_instruction),
            LLMMessage.user(question),
        ]
        response = await generate(
            messages=messages,
            model=Config.get_config("help", "DEFAULT_LLM_MODEL"),
        )

        reply_text = response.text if response else "抱歉，我暂时无法回答这个问题。"
        threshold = Config.get_config("help", "LLM_HELPER_REPLY_AS_IMAGE_THRESHOLD", 50)
        if len(reply_text) > threshold:
            markdown = Markdown()
            markdown.text(reply_text)
            return await markdown.build()
        return reply_text

    except LLMException as e:
        logger.error(f"LLM智能帮助出错: {e}", "帮助", e=e)
        return "抱歉，智能帮助功能当前不可用，请稍后再试或联系管理员。"
    except Exception as e:
        logger.error(f"构建LLM帮助时发生未知错误: {e}", "帮助", e=e)
        return "抱歉，智能帮助功能遇到了一点小问题，正在紧急处理中！"
