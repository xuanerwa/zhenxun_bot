"""
动态标签的规则执行结果模型。
"""

from abc import ABC

from pydantic import BaseModel
from tortoise.expressions import Q


class RuleExecutionError(ValueError):
    """在规则执行期间，由处理器返回的、可向用户展示的错误。"""

    pass


class RuleExecutionResult(BaseModel, ABC):
    """规则执行结果的抽象基类。"""

    pass


class QueryResult(RuleExecutionResult):
    """表示数据库查询条件的结果。"""

    q_object: Q

    class Config:
        arbitrary_types_allowed = True


class IDSetResult(RuleExecutionResult):
    """表示一组群组ID的结果。"""

    group_ids: set[str]


class ErrorResult(RuleExecutionResult):
    """表示一个可向用户显示的错误。"""

    message: str
