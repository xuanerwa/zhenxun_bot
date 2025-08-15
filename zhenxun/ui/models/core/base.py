"""
核心基础模型定义
用于存放 RenderableComponent 基类
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

__all__ = ["RenderableComponent"]


class RenderableComponent(BaseModel, ABC):
    """所有可渲染UI组件的抽象基类。"""

    @property
    @abstractmethod
    def template_name(self) -> str:
        """返回用于渲染此组件的Jinja2模板的路径。"""
        pass
