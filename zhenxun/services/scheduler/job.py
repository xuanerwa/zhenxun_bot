"""
定时任务的执行逻辑

包含被 APScheduler 实际调度的函数，以及处理不同目标（单个、所有群组）的执行策略。
"""

import asyncio
import copy
from functools import partial
import random

import nonebot
from nonebot.adapters import Bot
from nonebot.dependencies import Dependent
from nonebot.exception import FinishedException, PausedException, SkippedException
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from pydantic import BaseModel, Field

from zhenxun.configs.config import Config
from zhenxun.models.scheduled_job import ScheduledJob
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.decorator.retry import Retry
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.pydantic_compat import parse_as

SCHEDULE_CONCURRENCY_KEY = "all_groups_concurrency_limit"


class ScheduleContext(BaseModel):
    """
    定时任务执行上下文，可通过依赖注入获取。
    """

    schedule_id: int = Field(..., description="数据库中的任务ID")
    plugin_name: str = Field(..., description="任务所属的插件名称")
    bot_id: str | None = Field(None, description="执行任务的Bot ID")
    group_id: str | None = Field(None, description="任务目标群组ID")
    job_kwargs: dict = Field(default_factory=dict, description="任务配置的参数")


async def _execute_single_job_instance(schedule: ScheduledJob, bot):
    """
    负责执行一个具体目标的任务实例。
    """
    plugin_name = schedule.plugin_name
    group_id = schedule.group_id

    from .service import ExecutionPolicy, scheduler_manager

    task_meta = scheduler_manager._registered_tasks.get(plugin_name)

    if not task_meta:
        logger.error(f"无法执行任务：插件 '{plugin_name}' 在执行期间变得不可用。")
        return

    is_blocked = await CommonUtils.task_is_block(bot, plugin_name, group_id)
    if is_blocked:
        target_desc = f"群 {group_id}" if group_id else "全局"
        logger.info(
            f"插件 '{plugin_name}' 的定时任务在目标 [{target_desc}] "
            f"因功能被禁用而跳过执行。"
        )
        return

    context = ScheduleContext(
        schedule_id=schedule.id,
        plugin_name=schedule.plugin_name,
        bot_id=bot.self_id,
        group_id=schedule.group_id,
        job_kwargs=schedule.job_kwargs if isinstance(schedule.job_kwargs, dict) else {},
    )
    state: T_State = {ScheduleContext: context}

    policy_data = context.job_kwargs.pop("execution_policy", {})
    policy = ExecutionPolicy(**policy_data)

    async def task_execution_coro():
        injected_params = {"context": context}

        params_model = task_meta.get("model")
        if params_model and isinstance(context.job_kwargs, dict):
            try:
                if isinstance(params_model, type) and issubclass(
                    params_model, BaseModel
                ):
                    params_instance = parse_as(params_model, context.job_kwargs)
                    injected_params["params"] = params_instance  # type: ignore
            except Exception as e:
                logger.error(
                    f"任务 {schedule.id} (目标: {group_id}) 参数验证失败: {e}", e=e
                )
                raise

        async def wrapper(bot: Bot):
            return await task_meta["func"](bot=bot, **injected_params)  # type: ignore

        dependent = Dependent.parse(
            call=wrapper,
            allow_types=Matcher.HANDLER_PARAM_TYPES,
        )
        return await dependent(bot=bot, state=state)

    try:
        if policy.retries > 0:
            on_success_handler = None
            if policy.on_success_callback:
                on_success_handler = partial(policy.on_success_callback, context)

            on_failure_handler = None
            if policy.on_failure_callback:
                on_failure_handler = partial(policy.on_failure_callback, context)

            retry_exceptions = tuple(policy.retry_on_exceptions or [])

            retry_decorator = Retry.api(
                stop_max_attempt=policy.retries + 1,
                strategy="exponential" if policy.retry_backoff else "fixed",
                wait_fixed_seconds=policy.retry_delay_seconds,
                exception=retry_exceptions,
                on_success=on_success_handler,
                on_failure=on_failure_handler,
                log_name=f"ScheduledJob-{schedule.id}-{schedule.group_id or 'global'}",
            )

            decorated_executor = retry_decorator(task_execution_coro)
            await decorated_executor()
        else:
            logger.info(
                f"插件 '{plugin_name}' 开始为目标 [{group_id or '全局'}] "
                f"执行定时任务 (ID: {schedule.id})。"
            )
            await task_execution_coro()

    except (PausedException, FinishedException, SkippedException) as e:
        logger.warning(
            f"定时任务 {schedule.id} (目标: {group_id}) 被中断: {type(e).__name__}"
        )
    except Exception as e:
        logger.error(
            f"执行定时任务 {schedule.id} (目标: {group_id}) "
            f"时发生未被策略处理的最终错误",
            e=e,
        )


async def _execute_job(schedule_id: int):
    """
    APScheduler 调度的入口函数，现在作为分发器。
    """
    from .repository import ScheduleRepository
    from .service import scheduler_manager

    scheduler_manager._running_tasks.add(schedule_id)
    try:
        schedule = await ScheduleRepository.get_by_id(schedule_id)
        if not schedule or not schedule.is_enabled:
            logger.warning(f"定时任务 {schedule_id} 不存在或已禁用，跳过执行。")
            return

        if schedule.plugin_name not in scheduler_manager._registered_tasks:
            logger.error(
                f"无法执行定时任务：插件 '{schedule.plugin_name}' "
                f"未注册或已卸载。将禁用该任务。"
            )
            schedule.is_enabled = False
            await ScheduleRepository.save(schedule, update_fields=["is_enabled"])
            from .adapter import APSchedulerAdapter

            APSchedulerAdapter.remove_job(schedule.id)
            return

        try:
            bot = (
                nonebot.get_bot(schedule.bot_id)
                if schedule.bot_id
                else nonebot.get_bot()
            )
        except (KeyError, ValueError):
            logger.warning(
                f"定时任务 {schedule_id} 需要的 Bot {schedule.bot_id} "
                f"不在线，本次执行跳过。"
            )
            return

        if schedule.group_id == scheduler_manager.ALL_GROUPS:
            concurrency_limit = Config.get_config(
                "SchedulerManager", SCHEDULE_CONCURRENCY_KEY, 5
            )
            if not isinstance(concurrency_limit, int) or concurrency_limit <= 0:
                concurrency_limit = 5

            logger.info(
                f"开始执行针对 [所有群组] 的任务 (ID: {schedule.id}, "
                f"插件: {schedule.plugin_name}, Bot: {bot.self_id})，"
                f"并发限制: {concurrency_limit}"
            )

            try:
                group_list, _ = await PlatformUtils.get_group_list(bot)
                all_gids = {
                    g.group_id for g in group_list if g.group_id and not g.channel_id
                }
            except Exception as e:
                logger.error(f"为 'all' 任务获取 Bot {bot.self_id} 的群列表失败", e=e)
                return

            specific_tasks_gids = set(
                await ScheduledJob.filter(
                    plugin_name=schedule.plugin_name, group_id__in=list(all_gids)
                ).values_list("group_id", flat=True)
            )

            semaphore = asyncio.Semaphore(concurrency_limit)

            async def worker(gid: str):
                await asyncio.sleep(random.uniform(0.1, 1.0))
                async with semaphore:
                    temp_schedule = copy.deepcopy(schedule)
                    temp_schedule.group_id = gid
                    await _execute_single_job_instance(temp_schedule, bot)

            tasks_to_run = [
                worker(gid) for gid in all_gids if gid not in specific_tasks_gids
            ]

            if tasks_to_run:
                await asyncio.gather(*tasks_to_run)
            logger.info(
                f"针对 [所有群组] 的任务 (ID: {schedule.id}) 执行完毕，"
                f"共处理 {len(tasks_to_run)} 个群组。"
            )

        else:
            await _execute_single_job_instance(schedule, bot)

    finally:
        scheduler_manager._running_tasks.discard(schedule_id)
