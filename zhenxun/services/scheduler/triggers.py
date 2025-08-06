from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BaseTrigger(BaseModel):
    """触发器配置的基类"""

    trigger_type: str = Field(..., exclude=True)


class CronTrigger(BaseTrigger):
    """Cron 触发器配置"""

    trigger_type: Literal["cron"] = "cron"  # type: ignore
    year: int | str | None = None
    month: int | str | None = None
    day: int | str | None = None
    week: int | str | None = None
    day_of_week: int | str | None = None
    hour: int | str | None = None
    minute: int | str | None = None
    second: int | str | None = None
    start_date: datetime | str | None = None
    end_date: datetime | str | None = None
    timezone: str | None = None
    jitter: int | None = None


class IntervalTrigger(BaseTrigger):
    """Interval 触发器配置"""

    trigger_type: Literal["interval"] = "interval"  # type: ignore
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    start_date: datetime | str | None = None
    end_date: datetime | str | None = None
    timezone: str | None = None
    jitter: int | None = None


class DateTrigger(BaseTrigger):
    """Date 触发器配置"""

    trigger_type: Literal["date"] = "date"  # type: ignore
    run_date: datetime | str
    timezone: str | None = None


class Trigger:
    """
    一个用于创建类型安全触发器配置的工厂类。
    提供了流畅的、具备IDE自动补全功能的API。

    使用示例:
        from zhenxun.services.scheduler import Trigger

        @scheduler.job(trigger=Trigger.cron(hour=8))
        async def my_task():
            ...
    """

    @staticmethod
    def cron(**kwargs) -> CronTrigger:
        """创建一个 Cron 触发器配置。"""
        return CronTrigger(**kwargs)

    @staticmethod
    def interval(**kwargs) -> IntervalTrigger:
        """创建一个 Interval 触发器配置。"""
        return IntervalTrigger(**kwargs)

    @staticmethod
    def date(**kwargs) -> DateTrigger:
        """创建一个 Date 触发器配置。"""
        return DateTrigger(**kwargs)
