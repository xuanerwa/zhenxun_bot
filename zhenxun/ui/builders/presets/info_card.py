from typing import Any

from ...models.presets.card import (
    InfoCardData,
    InfoCardMetadataItem,
    InfoCardSection,
)
from ..base import BaseBuilder

__all__ = ["InfoCardBuilder"]


class InfoCardBuilder(BaseBuilder[InfoCardData]):
    def __init__(self, title: str):
        self._data = InfoCardData(title=title)

        super().__init__(self._data, template_name="components/presets/info_card")

    def add_metadata(self, label: str, value: str | int) -> "InfoCardBuilder":
        self._data.metadata.append(InfoCardMetadataItem(label=label, value=value))
        return self

    def add_metadata_items(
        self, items: list[tuple[str, Any]] | list[dict[str, Any]]
    ) -> "InfoCardBuilder":
        for item in items:
            if isinstance(item, tuple):
                self.add_metadata(item[0], item[1])
            elif isinstance(item, dict):
                self.add_metadata(item.get("label", ""), item.get("value", ""))
        return self

    def add_section(self, title: str, content: str | list[str]) -> "InfoCardBuilder":
        content_list = [content] if isinstance(content, str) else content
        self._data.sections.append(InfoCardSection(title=title, content=content_list))
        return self

    def add_sections(
        self, sections: list[tuple[str, str | list[str]]] | list[dict[str, Any]]
    ) -> "InfoCardBuilder":
        for section in sections:
            if isinstance(section, tuple):
                self.add_section(section[0], section[1])
            elif isinstance(section, dict):
                self.add_section(section.get("title", ""), section.get("content", []))
        return self
