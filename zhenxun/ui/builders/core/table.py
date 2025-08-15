from ...models.core.table import TableCell, TableData
from ..base import BaseBuilder

__all__ = ["TableBuilder"]


class TableBuilder(BaseBuilder[TableData]):
    """链式构建通用表格的辅助类"""

    def __init__(self, title: str, tip: str | None = None):
        data_model = TableData(title=title, tip=tip, headers=[], rows=[])
        super().__init__(data_model, template_name="components/core/table")

    def set_headers(self, headers: list[str]) -> "TableBuilder":
        """设置表头"""
        self._data.headers = headers
        return self

    def add_row(self, row: list[TableCell]) -> "TableBuilder":
        """添加单行数据"""
        self._data.rows.append(row)
        return self

    def add_rows(self, rows: list[list[TableCell]]) -> "TableBuilder":
        """批量添加多行数据"""
        self._data.rows.extend(rows)
        return self
