from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

import aiofiles
from pydantic import BaseModel, Field

from zhenxun.services.log import logger

from .base import RenderableComponent

__all__ = [
    "CodeElement",
    "HeadingElement",
    "ImageElement",
    "ListElement",
    "ListItemElement",
    "MarkdownData",
    "MarkdownElement",
    "QuoteElement",
    "RawHtmlElement",
    "TableElement",
    "TextElement",
]


class MarkdownElement(BaseModel, ABC):
    @abstractmethod
    def to_markdown(self) -> str:
        """Serializes the element to its Markdown string representation."""
        pass


class TextElement(MarkdownElement):
    text: str

    def to_markdown(self) -> str:
        return self.text


class HeadingElement(MarkdownElement):
    text: str
    level: int = Field(..., ge=1, le=6)

    def to_markdown(self) -> str:
        return f"{'#' * self.level} {self.text}"


class ImageElement(MarkdownElement):
    src: str
    alt: str = "image"

    def to_markdown(self) -> str:
        return f"![{self.alt}]({self.src})"


class CodeElement(MarkdownElement):
    code: str
    language: str = ""

    def to_markdown(self) -> str:
        return f"```{self.language}\n{self.code}\n```"


class RawHtmlElement(MarkdownElement):
    html: str

    def to_markdown(self) -> str:
        return self.html


class TableElement(MarkdownElement):
    headers: list[str]
    rows: list[list[str]]
    alignments: list[Literal["left", "center", "right"]] | None = None

    def to_markdown(self) -> str:
        header_row = "| " + " | ".join(self.headers) + " |"

        if self.alignments:
            align_map = {"left": ":---", "center": ":---:", "right": "---:"}
            separator_row = (
                "| "
                + " | ".join([align_map.get(a, "---") for a in self.alignments])
                + " |"
            )
        else:
            separator_row = "| " + " | ".join(["---"] * len(self.headers)) + " |"

        data_rows = "\n".join(
            "| " + " | ".join(map(str, row)) + " |" for row in self.rows
        )
        return f"{header_row}\n{separator_row}\n{data_rows}"


class ContainerElement(MarkdownElement):
    content: list[MarkdownElement] = Field(default_factory=list)


class QuoteElement(ContainerElement):
    def to_markdown(self) -> str:
        inner_md = "\n".join(part.to_markdown() for part in self.content)
        return "\n".join([f"> {line}" for line in inner_md.split("\n")])


class ListItemElement(ContainerElement):
    def to_markdown(self) -> str:
        return "\n".join(part.to_markdown() for part in self.content)


class ListElement(ContainerElement):
    ordered: bool = False

    def to_markdown(self) -> str:
        lines = []
        for i, item in enumerate(self.content):
            if isinstance(item, ListItemElement):
                prefix = f"{i + 1}." if self.ordered else "*"
                item_content = item.to_markdown()
                lines.append(f"{prefix} {item_content}")
        return "\n".join(lines)


class MarkdownData(RenderableComponent):
    """Markdown转图片的数据模型"""

    style_name: str | None = None
    markdown: str
    width: int = 800
    css_path: str | None = None

    @property
    def template_name(self) -> str:
        return "components/core/markdown"

    async def get_extra_css(self, theme_manager) -> str:
        if self.css_path:
            css_file = Path(self.css_path)
            if css_file.is_file():
                async with aiofiles.open(css_file, encoding="utf-8") as f:
                    return await f.read()
            else:
                logger.warning(f"Markdown自定义CSS文件不存在: {self.css_path}")
        else:
            style_name = self.style_name or "github-light"
            css_path = (
                theme_manager.current_theme.default_assets_dir
                / "css"
                / "markdown"
                / f"{style_name}.css"
            )
            if css_path.exists():
                async with aiofiles.open(css_path, encoding="utf-8") as f:
                    return await f.read()
        return ""
