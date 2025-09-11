from pathlib import Path
from typing import Any, Literal

from ...models.core.table import (
    BaseCell,
    ImageCell,
    TableCell,
    TableData,
    TextCell,
)
from ..base import BaseBuilder

__all__ = ["TableBuilder"]


class TableBuilder(BaseBuilder[TableData]):
    """链式构建通用表格的辅助类"""

    def __init__(self, title: str, tip: str | None = None):
        data_model = TableData(title=title, tip=tip, headers=[], rows=[])
        super().__init__(data_model, template_name="components/core/table")

    def _normalize_cell(self, cell_data: Any) -> TableCell:
        """内部辅助方法，将各种原生数据类型转换为TableCell模型。"""
        if isinstance(cell_data, BaseCell):
            return cell_data  # type: ignore
        if isinstance(cell_data, str | int | float):
            return TextCell(content=str(cell_data))
        if isinstance(cell_data, Path):
            return ImageCell(src=cell_data.resolve().as_uri())
        if isinstance(cell_data, tuple) and len(cell_data) == 3:
            if (
                isinstance(cell_data[0], Path)
                and isinstance(cell_data[1], int)
                and isinstance(cell_data[2], int)
            ):
                return ImageCell(
                    src=cell_data[0].resolve().as_uri(),
                    width=cell_data[1],
                    height=cell_data[2],
                )

        return TextCell(content="")

    def set_headers(self, headers: list[str]) -> "TableBuilder":
        """
        设置表格的表头。

        参数:
            headers: 一个包含表头文本的字符串列表。

        返回:
            TableBuilder: 当前构建器实例，以支持链式调用。
        """
        self._data.headers = headers
        return self

    def set_column_alignments(
        self, alignments: list[Literal["left", "center", "right"]]
    ) -> "TableBuilder":
        """
        设置表格每列的文本对齐方式。

        参数:
            alignments: 一个包含 'left', 'center', 'right' 的对齐方式列表。

        返回:
            TableBuilder: 当前构建器实例，以支持链式调用。
        """
        self._data.column_alignments = alignments
        return self

    def set_column_widths(self, widths: list[str | int]) -> "TableBuilder":
        """设置每列的宽度"""
        self._data.column_widths = widths
        return self

    def add_row(self, row: list[TableCell]) -> "TableBuilder":
        """
        向表格中添加一行数据。

        参数:
            row: 一个包含单元格数据的列表。单元格可以是字符串、数字或
                 `TextCell`, `ImageCell` 等模型实例。

        返回:
            TableBuilder: 当前构建器实例，以支持链式调用。
        """
        normalized_row = [self._normalize_cell(cell) for cell in row]
        self._data.rows.append(normalized_row)
        return self

    def add_rows(self, rows: list[list[TableCell]]) -> "TableBuilder":
        """
        向表格中批量添加多行数据, 并自动转换原生类型。

        参数:
            rows: 一个包含多行数据的列表。

        返回:
            TableBuilder: 当前构建器实例，以支持链式调用。
        """
        for row in rows:
            self.add_row(row)
        return self
