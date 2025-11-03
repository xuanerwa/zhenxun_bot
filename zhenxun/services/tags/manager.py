"""
标签服务的核心实现，负责标签的增删改查与动态规则解析。
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar

from aiocache import Cache, cached
from arclet.alconna import Alconna, Args
from nonebot.adapters import Bot
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from zhenxun.models.group_console import GroupConsole
from zhenxun.models.group_tag import GroupTag, GroupTagLink
from zhenxun.services.log import logger
from zhenxun.utils.platform import PlatformUtils

from .models import (
    ErrorResult,
    IDSetResult,
    QueryResult,
    RuleExecutionError,
    RuleExecutionResult,
)


@dataclass
class HandlerInfo:
    """存储已注册处理器的元信息。"""

    func: Callable[..., Coroutine[Any, Any, RuleExecutionResult]]
    alconna: Alconna


def invalidate_on_change(func: Callable) -> Callable:
    """装饰器: 在方法成功执行后自动使标签缓存失效。"""

    async def wrapper(self: "TagManager", *args, **kwargs):
        result = await func(self, *args, **kwargs)
        await self._invalidate_cache()
        return result

    return wrapper


class TagManager:
    """群组标签管理服务。提供对群组标签的注册、解析与维护等操作。"""

    _dynamic_handlers: ClassVar[dict[str, HandlerInfo]] = {}

    def add_field_rule(self, name: str, db_field: str, value_type: type):
        """
        一个便捷的快捷方式，用于快速创建一个基于 `GroupConsole` 模型字段的规则。
        它在内部使用 `register_rule`。
        """
        from arclet.alconna import CommandMeta

        alc = Alconna(
            name,
            Args["op", str]["value", value_type],
            meta=CommandMeta(
                fuzzy_match=True,
                compact=False,
            ),
        )

        handler = partial(self._generic_field_handler, db_field=db_field)

        self.register_rule(alc)(handler)

        logger.debug(f"已添加字段规则: '{name}' -> {db_field} ({value_type.__name__})")

    async def _generic_field_handler(
        self, db_field: str, op: str, value: Any
    ) -> QueryResult:
        """所有通过 add_field_rule 添加的规则共享的处理器。"""
        op_map = {">": "__gt", ">=": "__gte", "<": "__lt", "<=": "__lte", "=": ""}
        op_lower = op.lower()

        if op_lower == "contains":
            op_suffix = "__iposix_regex"
        elif op_lower == "in":
            op_suffix = "__in"
            value = [v.strip() for v in str(value).split(",")]
        elif op == "!=":
            return QueryResult(q_object=~Q(**{db_field: value}))
        elif op in op_map:
            op_suffix = op_map[op]
        else:
            raise RuleExecutionError(f"字段 '{db_field}' 不支持操作符: {op}")

        q_kwargs: dict[str, Any] = {
            f"{db_field}{op_suffix}" if op_suffix else db_field: value
        }
        return QueryResult(q_object=Q(**q_kwargs))

    def register_rule(self, alconna: Alconna):
        """
        装饰器：注册一个完全自定义的规则处理器及其语法定义(Alconna)。
        """

        def decorator(handler: Callable[..., Coroutine[Any, Any, RuleExecutionResult]]):
            name = alconna.command
            if name in self._dynamic_handlers:
                logger.warning(f"动态标签规则 '{name}' 已被注册，将被覆盖。")
            self._dynamic_handlers[name] = HandlerInfo(func=handler, alconna=alconna)
            logger.debug(f"已注册动态标签规则: '{name}'")
            return handler

        return decorator

    async def _invalidate_cache(self):
        """辅助函数，用于清除标签相关的缓存，确保数据一致性。"""
        cache = Cache(Cache.MEMORY, namespace="tag_service")
        await cache.clear()
        logger.debug("已清除所有群组标签缓存。")

    @invalidate_on_change
    async def create_tag(
        self,
        name: str,
        is_blacklist: bool = False,
        description: str | None = None,
        group_ids: list[str] | None = None,
        tag_type: str = "STATIC",
        dynamic_rule: dict | str | None = None,
    ) -> GroupTag:
        """
        创建新的群组标签。

        参数：
            name: 标签名称。
            is_blacklist: 是否为黑名单标签，黑名单标签会在最终结果中剔除关联群组。
            description: 标签描述信息。
            group_ids: 需要关联的静态群组 ID 列表，动态标签必须留空。
            tag_type: 标签类型，支持 ``STATIC`` 或 ``DYNAMIC``。
            dynamic_rule: 动态标签所使用的规则配置。

        返回：
            新创建的 ``GroupTag`` 实例。
        """
        if tag_type == "DYNAMIC" and group_ids:
            raise ValueError("动态标签不能在创建时关联静态群组。")
        if tag_type == "STATIC" and dynamic_rule:
            raise ValueError("静态标签不能设置动态规则。")
        async with in_transaction():
            tag = await GroupTag.create(
                name=name,
                is_blacklist=is_blacklist,
                description=description,
                tag_type=tag_type,
                dynamic_rule=dynamic_rule,
            )
            if group_ids:
                await GroupTagLink.bulk_create(
                    [GroupTagLink(tag=tag, group_id=gid) for gid in group_ids]
                )
            return tag

    @invalidate_on_change
    async def delete_tag(self, name: str) -> bool:
        """
        删除指定标签。

        参数：
            name: 标签名称。

        返回：
            ``True`` 表示删除成功，``False`` 表示标签不存在。
        """
        deleted_count = await GroupTag.filter(name=name).delete()
        return deleted_count > 0

    @invalidate_on_change
    async def add_groups_to_tag(self, name: str, group_ids: list[str]) -> int:  # type: ignore
        """
        向静态标签追加群组关联。
        """
        tag = await GroupTag.get_or_none(name=name)
        if not tag:
            raise ValueError(f"标签 '{name}' 不存在。")
        if tag.tag_type == "DYNAMIC":
            raise ValueError("不能向动态标签手动添加群组。")

        await GroupTagLink.bulk_create(
            [GroupTagLink(tag=tag, group_id=gid) for gid in group_ids],
            ignore_conflicts=True,
        )
        return len(group_ids)

    @invalidate_on_change
    async def remove_groups_from_tag(self, name: str, group_ids: list[str]) -> int:
        """从静态标签移除指定群组。"""
        tag = await GroupTag.get_or_none(name=name)
        if not tag:
            return 0
        if tag.tag_type == "DYNAMIC":
            raise ValueError("不能从动态标签手动移除群组。")
        deleted_count = await GroupTagLink.filter(
            tag=tag, group_id__in=group_ids
        ).delete()
        return deleted_count

    async def list_tags_with_counts(self) -> list[dict]:
        """列出所有标签及其关联的群组数量。"""
        tags = await GroupTag.all().prefetch_related("groups")
        return [
            {
                "name": tag.name,
                "description": tag.description,
                "is_blacklist": tag.is_blacklist,
                "tag_type": tag.tag_type,
                "group_count": len(tag.groups),
            }
            for tag in tags
        ]

    async def get_tag_details(self, name: str, bot: Bot | None = None) -> dict | None:
        """
        获取标签的完整信息，包括基础属性、静态群组与动态解析结果。

        参数：
            name: 标签名称。
            bot: 可选的 ``Bot`` 实例，用于在动态标签下获取实时群组信息。

        返回：
            包含标签详情的字典；若标签不存在则返回 ``None``。
        """
        tag = await GroupTag.get_or_none(name=name).prefetch_related("groups")
        if not tag:
            return None

        final_group_ids = await self.resolve_tag_to_group_ids(name, bot=bot)
        resolved_groups: list[tuple[str, str]] = []
        if final_group_ids:
            groups_from_db = await GroupConsole.filter(
                group_id__in=final_group_ids
            ).all()
            resolved_groups = [(g.group_id, g.group_name) for g in groups_from_db]

        return {
            "name": tag.name,
            "description": tag.description,
            "is_blacklist": tag.is_blacklist,
            "tag_type": tag.tag_type,
            "dynamic_rule": tag.dynamic_rule,
            "groups": [link.group_id for link in tag.groups],
            "resolved_groups": resolved_groups,
        }

    async def _execute_rule(
        self, rule_str: str, bot: Bot | None
    ) -> RuleExecutionResult:
        """使用Alconna解析并执行单个规则。"""
        rule_str = " ".join(rule_str.split())

        parts = rule_str.strip().split(maxsplit=1)
        if not parts:
            raise RuleExecutionError("规则字符串不能为空")

        rule_name = parts[0]

        handler_info = self._dynamic_handlers.get(rule_name)
        if not handler_info:
            available_rules = ", ".join(sorted(self._dynamic_handlers.keys()))
            raise RuleExecutionError(
                f"未知的规则名称: '{rule_name}'\n可用规则: {available_rules}"
            )

        try:
            arparma = handler_info.alconna.parse(rule_str)
            if not arparma.matched:
                error_msg = (
                    str(arparma.error_info) if arparma.error_info else "未知语法错误"
                )

                args_info = []
                if handler_info.alconna.args:
                    for arg in handler_info.alconna.args.argument:
                        arg_name = arg.name
                        arg_type = getattr(arg.value, "origin", arg.value)
                        type_name = getattr(arg_type, "__name__", str(arg_type))
                        args_info.append(f"<{arg_name}:{type_name}>")

                expected_format = (
                    f"{rule_name} {' '.join(args_info)}" if args_info else rule_name
                )

                example = ""
                if rule_name in ["member_count", "level"]:
                    example = f"\n示例: {rule_name} > 100"
                elif rule_name in ["status", "is_super"]:
                    example = f"\n示例: {rule_name} = true"
                elif rule_name == "group_name":
                    example = f"\n示例: {rule_name} contains 测试"

                raise RuleExecutionError(
                    f"规则 '{rule_name}' 参数错误: {error_msg}\n"
                    f"期望格式: {expected_format}{example}"
                )

            func_to_check = (
                handler_info.func.func
                if isinstance(handler_info.func, partial)
                else handler_info.func
            )

            extra_kwargs = {}
            if "bot" in getattr(func_to_check, "__annotations__", {}):
                extra_kwargs["bot"] = bot

            result = await arparma.call(handler_info.func, **extra_kwargs)

            if not isinstance(result, RuleExecutionResult):
                raise TypeError(
                    f"处理器 '{rule_name}' 返回了不支持的类型 '{type(result)}'。 "
                    "必须返回 QueryResult, IDSetResult 或 ErrorResult。"
                )
            return result

        except RuleExecutionError:
            raise
        except Exception as e:
            raise RuleExecutionError(f"执行规则 '{rule_name}' 时发生内部错误: {e}")

    async def _resolve_dynamic_tag(
        self, rule: dict | str, bot: Bot | None = None
    ) -> set[str]:
        """根据动态规则解析符合条件的群组 ID 集合。"""
        if isinstance(rule, dict):
            raise RuleExecutionError("动态规则必须是字符串格式。")

        final_ids: set[str] = set()
        or_clauses = [part.strip() for part in rule.split(" or ")]

        for or_clause in or_clauses:
            current_and_q = Q()
            current_and_ids: set[str] | None = None

            and_rules = [part.strip() for part in or_clause.split(" and ")]
            for simple_rule in and_rules:
                try:
                    result = await self._execute_rule(simple_rule, bot)
                    if isinstance(result, QueryResult):
                        current_and_q &= result.q_object
                    elif isinstance(result, IDSetResult):
                        if current_and_ids is None:
                            current_and_ids = result.group_ids
                        else:
                            current_and_ids.intersection_update(result.group_ids)
                    elif isinstance(result, ErrorResult):
                        raise RuleExecutionError(result.message)

                except Exception as e:
                    raise RuleExecutionError(
                        f"解析规则 '{simple_rule}' 时失败: {e}"
                    ) from e

            ids_from_q: set[str] | None = None
            if current_and_q.children:
                q_filtered_groups = await GroupConsole.filter(
                    current_and_q
                ).values_list("group_id", flat=True)
                ids_from_q = {str(gid) for gid in q_filtered_groups}

            if ids_from_q is not None:
                if current_and_ids is None:
                    clause_result_ids = ids_from_q
                else:
                    clause_result_ids = current_and_ids.intersection(ids_from_q)
            else:
                if current_and_ids is None:
                    clause_result_ids = set()
                else:
                    clause_result_ids = current_and_ids

            final_ids.update(clause_result_ids)

        if bot:
            bot_groups, _ = await PlatformUtils.get_group_list(bot)
            bot_group_ids = {g.group_id for g in bot_groups if g.group_id}
            final_ids.intersection_update(bot_group_ids)

        return final_ids

    @cached(ttl=300, namespace="tag_service")
    async def resolve_tag_to_group_ids(
        self, name: str, bot: Bot | None = None
    ) -> list[str]:
        """
        核心解析方法：根据标签名解析出最终的群组ID列表

        参数：
            name: 需要解析的标签名称，特殊值 ``@all`` 表示所有群。
            bot: 可选的 ``Bot`` 实例，用于拉取最新的群信息。

        返回：
            标签对应的群组 ID 列表。当标签不存在或无法解析时返回空列表。
        """
        if name == "@all":
            if bot:
                all_groups, _ = await PlatformUtils.get_group_list(bot)
                return [str(g.group_id) for g in all_groups if g.group_id]
            else:
                all_group_ids = await GroupConsole.all().values_list(
                    "group_id", flat=True
                )
                return [str(gid) for gid in all_group_ids]

        tag = await GroupTag.get_or_none(name=name).prefetch_related("groups")
        if not tag:
            return []

        associated_groups: set[str] = set()
        if tag.tag_type == "STATIC":
            associated_groups = {str(link.group_id) for link in tag.groups}
        elif tag.tag_type == "DYNAMIC":
            if not tag.dynamic_rule or not isinstance(tag.dynamic_rule, dict | str):
                return []
            dynamic_ids = await self._resolve_dynamic_tag(tag.dynamic_rule, bot)
            associated_groups = {str(gid) for gid in dynamic_ids}
        else:
            associated_groups = {str(link.group_id) for link in tag.groups}

        if tag.is_blacklist:
            all_groups_query = GroupConsole.all()
            if bot:
                bot_groups, _ = await PlatformUtils.get_group_list(bot)
                bot_group_ids = {str(g.group_id) for g in bot_groups if g.group_id}
                if bot_group_ids:
                    all_groups_query = all_groups_query.filter(
                        group_id__in=bot_group_ids
                    )
                else:
                    return []

            all_relevant_group_ids_from_db = await all_groups_query.values_list(
                "group_id", flat=True
            )
            all_relevant_group_ids = {
                str(gid) for gid in all_relevant_group_ids_from_db
            }

            return list(all_relevant_group_ids - associated_groups)
        else:
            return list(associated_groups)

    @invalidate_on_change
    async def rename_tag(self, old_name: str, new_name: str) -> GroupTag:
        """重命名已有标签"""
        if await GroupTag.exists(name=new_name):
            raise IntegrityError(f"标签 '{new_name}' 已存在。")
        tag = await GroupTag.get(name=old_name)
        tag.name = new_name
        await tag.save(update_fields=["name"])
        return tag

    @invalidate_on_change
    async def update_tag_attributes(
        self,
        name: str,
        description: str | None = None,
        is_blacklist: bool | None = None,
        dynamic_rule: dict | str | None = None,
    ) -> GroupTag:
        """
        局部更新标签属性。

        参数：
            name: 标签名称。
            description: 可选的新描述。
            is_blacklist: 可选的新黑名单标记。
            dynamic_rule: 可选的新动态规则配置。

        返回：
            更新后的 ``GroupTag`` 实例。
        """
        tag = await GroupTag.get(name=name)
        update_fields = []
        if dynamic_rule is not None:
            if tag.tag_type != "DYNAMIC":
                raise ValueError("只能为动态标签更新规则。")
            tag.dynamic_rule = dynamic_rule  # type: ignore
            update_fields.append("dynamic_rule")
        if description is not None:
            tag.description = description
            update_fields.append("description")
        if is_blacklist is not None:
            tag.is_blacklist = is_blacklist
            update_fields.append("is_blacklist")

        if update_fields:
            await tag.save(update_fields=update_fields)
        return tag

    @invalidate_on_change
    async def set_groups_for_tag(self, name: str, group_ids: list[str]) -> int:
        """
        覆盖设置静态标签的群组列表。

        参数：
            name: 标签名称。
            group_ids: 需要绑定的群组 ID 列表。

        返回：
            设置成功后的群组数量。
        """
        tag = await GroupTag.get(name=name)
        if tag.tag_type == "DYNAMIC":
            raise ValueError("不能为动态标签设置静态群组列表。")
        async with in_transaction():
            await GroupTagLink.filter(tag=tag).delete()
            await GroupTagLink.bulk_create(
                [GroupTagLink(tag=tag, group_id=gid) for gid in group_ids],
                ignore_conflicts=True,
            )
        return len(group_ids)

    @invalidate_on_change
    async def clear_all_tags(self) -> int:
        """删除所有标签，并清空缓存。"""
        deleted_count = await GroupTag.all().delete()
        return deleted_count
