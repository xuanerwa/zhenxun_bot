"""
引擎适配层 (Adapter)

封装所有对具体调度器引擎 (APScheduler) 的操作，
使上层服务与调度器实现解耦。
"""

from collections.abc import Callable

from nonebot_plugin_apscheduler import scheduler

from zhenxun.models.scheduled_job import ScheduledJob
from zhenxun.services.log import logger

from .job import ScheduleContext, _execute_job

JOB_PREFIX = "zhenxun_schedule_"


class APSchedulerAdapter:
    """封装对 APScheduler 的操作"""

    @staticmethod
    def _get_job_id(schedule_id: int) -> str:
        """
        生成 APScheduler 的 Job ID

        参数:
            schedule_id: 定时任务的ID。

        返回:
            str: APScheduler 使用的 Job ID。
        """
        return f"{JOB_PREFIX}{schedule_id}"

    @staticmethod
    def add_or_reschedule_job(schedule: ScheduledJob):
        """
        根据 ScheduledJob 添加或重新调度一个 APScheduler 任务

        参数:
            schedule: 定时任务对象，包含任务的所有配置信息。
        """
        job_id = APSchedulerAdapter._get_job_id(schedule.id)

        if not isinstance(schedule.trigger_config, dict):
            logger.error(
                f"任务 {schedule.id} 的 trigger_config 不是字典类型: "
                f"{type(schedule.trigger_config)}"
            )
            return

        job = scheduler.get_job(job_id)
        if job:
            scheduler.reschedule_job(
                job_id, trigger=schedule.trigger_type, **schedule.trigger_config
            )
            logger.debug(f"已更新APScheduler任务: {job_id}")
        else:
            scheduler.add_job(
                _execute_job,
                trigger=schedule.trigger_type,
                id=job_id,
                misfire_grace_time=300,
                args=[schedule.id],
                **schedule.trigger_config,
            )
            logger.debug(f"已添加新的APScheduler任务: {job_id}")

    @staticmethod
    def remove_job(schedule_id: int):
        """
        移除一个 APScheduler 任务

        参数:
            schedule_id: 要移除的定时任务ID。
        """
        job_id = APSchedulerAdapter._get_job_id(schedule_id)
        try:
            scheduler.remove_job(job_id)
            logger.debug(f"已从APScheduler中移除任务: {job_id}")
        except Exception:
            pass

    @staticmethod
    def pause_job(schedule_id: int):
        """
        暂停一个 APScheduler 任务

        参数:
            schedule_id: 要暂停的定时任务ID。
        """
        job_id = APSchedulerAdapter._get_job_id(schedule_id)
        try:
            scheduler.pause_job(job_id)
        except Exception:
            pass

    @staticmethod
    def resume_job(schedule_id: int):
        """
        恢复一个 APScheduler 任务

        参数:
            schedule_id: 要恢复的定时任务ID。
        """
        job_id = APSchedulerAdapter._get_job_id(schedule_id)
        try:
            scheduler.resume_job(job_id)
        except Exception:
            import asyncio

            from .repository import ScheduleRepository

            async def _re_add_job():
                schedule = await ScheduleRepository.get_by_id(schedule_id)
                if schedule:
                    APSchedulerAdapter.add_or_reschedule_job(schedule)

            asyncio.create_task(_re_add_job())  # noqa: RUF006

    @staticmethod
    def get_job_status(schedule_id: int) -> dict:
        """
        获取 APScheduler Job 的状态

        参数:
            schedule_id: 定时任务的ID。

        返回:
            dict: 包含任务状态信息的字典，包含next_run_time等字段。
        """
        job_id = APSchedulerAdapter._get_job_id(schedule_id)
        job = scheduler.get_job(job_id)
        return {
            "next_run_time": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            if job and job.next_run_time
            else "N/A",
            "is_paused_in_scheduler": not bool(job.next_run_time) if job else "N/A",
        }

    @staticmethod
    def add_ephemeral_job(
        job_id: str,
        func: Callable,
        trigger_type: str,
        trigger_config: dict,
        context: ScheduleContext,
    ):
        """
        直接向 APScheduler 添加一个临时的、非持久化的任务

        参数:
            job_id: 临时任务的唯一ID。
            func: 要执行的函数。
            trigger_type: 触发器类型。
            trigger_config: 触发器配置字典。
            context: 任务执行上下文。
        """
        job = scheduler.get_job(job_id)
        if job:
            logger.warning(f"尝试添加一个已存在的临时任务ID: {job_id}，操作被忽略。")
            return

        scheduler.add_job(
            _execute_job,
            trigger=trigger_type,
            id=job_id,
            misfire_grace_time=60,
            args=[None],
            kwargs={"context_override": context},
            **trigger_config,
        )
        logger.debug(f"已添加新的临时APScheduler任务: {job_id}")
