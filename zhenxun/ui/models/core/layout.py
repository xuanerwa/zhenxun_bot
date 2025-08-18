from typing import Any

from pydantic import BaseModel, Field

from .base import ContainerComponent, RenderableComponent

__all__ = ["LayoutData", "LayoutItem"]


class LayoutItem(BaseModel):
    """布局中的单个项目，现在持有可渲染组件的数据模型"""

    component: RenderableComponent = Field(..., description="要渲染的组件的数据模型")
    metadata: dict[str, Any] | None = Field(None, description="传递给模板的额外元数据")
    html_content: str | None = None


class LayoutData(ContainerComponent):
    """布局构建器的数据模型"""

    style_name: str | None = None
    layout_type: str = "column"
    children: list[LayoutItem] = Field(
        default_factory=list, description="要布局的项目列表"
    )
    options: dict[str, Any] = Field(
        default_factory=dict, description="传递给模板的选项"
    )

    def get_required_scripts(self) -> list[str]:
        """[新增] 聚合所有子组件的脚本依赖。"""
        scripts = set()
        for item in self.children:
            scripts.update(item.component.get_required_scripts())
        return list(scripts)

    def get_required_styles(self) -> list[str]:
        """[新增] 聚合所有子组件的样式依赖。"""
        styles = set()
        for item in self.children:
            styles.update(item.component.get_required_styles())
        return list(styles)

    @property
    def template_name(self) -> str:
        return f"layouts/{self.layout_type}"

    def _get_renderable_child_items(self):
        yield from self.children
