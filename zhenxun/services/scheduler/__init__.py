"""
定时调度服务模块

提供一个统一的、持久化的定时任务管理器，供所有插件使用。
"""

from . import lifecycle
from .manager import scheduler_manager
from .types import ExecutionPolicy, ScheduleContext, Trigger

_ = lifecycle

__all__ = ["ExecutionPolicy", "ScheduleContext", "Trigger", "scheduler_manager"]
