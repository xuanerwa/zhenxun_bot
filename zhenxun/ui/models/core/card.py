from collections.abc import Iterable

from .base import ContainerComponent, RenderableComponent


class CardData(ContainerComponent):
    """通用卡片的数据模型，可以包含头部、内容和尾部"""

    header: RenderableComponent | None = None
    """卡片的头部内容组件"""
    content: RenderableComponent
    """卡片的主要内容组件"""
    footer: RenderableComponent | None = None
    """卡片的尾部内容组件"""

    @property
    def template_name(self) -> str:
        return "components/core/card"

    def get_children(self) -> Iterable[RenderableComponent]:
        """让CSS收集器能够遍历卡片的子组件"""
        if self.header:
            yield self.header
        if self.content:
            yield self.content
        if self.footer:
            yield self.footer
