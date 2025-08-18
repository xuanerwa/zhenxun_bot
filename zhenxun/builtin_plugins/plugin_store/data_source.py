from pathlib import Path
import random
import shutil

from aiocache import cached
import ujson as json

from zhenxun import ui
from zhenxun.builtin_plugins.plugin_store.models import StorePluginInfo
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.models.plugin_info import PluginInfo
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInitManager
from zhenxun.ui.builders import TableBuilder
from zhenxun.ui.models import StatusBadgeCell, TextCell
from zhenxun.utils.manager.virtual_env_package_manager import VirtualEnvPackageManager
from zhenxun.utils.repo_utils import RepoFileManager
from zhenxun.utils.repo_utils.models import RepoFileInfo, RepoType
from zhenxun.utils.utils import is_number

from .config import (
    BASE_PATH,
    DEFAULT_GITHUB_URL,
    EXTRA_GITHUB_URL,
    LOG_COMMAND,
)
from .exceptions import PluginStoreException


class StoreManager:
    @classmethod
    @cached(60)
    async def get_data(cls) -> tuple[list[StorePluginInfo], list[StorePluginInfo]]:
        """获取插件信息数据

        返回:
            tuple[list[StorePluginInfo], list[StorePluginInfo]]:
                原生插件信息数据，第三方插件信息数据
        """
        plugins = await RepoFileManager.get_file_content(
            DEFAULT_GITHUB_URL, "plugins.json"
        )
        extra_plugins = await RepoFileManager.get_file_content(
            EXTRA_GITHUB_URL, "plugins.json", "index"
        )
        return [StorePluginInfo(**plugin) for plugin in json.loads(plugins)], [
            StorePluginInfo(**plugin) for plugin in json.loads(extra_plugins)
        ]

    @classmethod
    def version_check(cls, plugin_info: StorePluginInfo, suc_plugin: dict[str, str]):
        """版本检查

        参数:
            plugin_info: StorePluginInfo
            suc_plugin: 模块名: 版本号

        返回:
            str: 版本号
        """
        module = plugin_info.module
        if suc_plugin.get(module) and not cls.check_version_is_new(
            plugin_info, suc_plugin
        ):
            return f"{suc_plugin[module]} (有更新->{plugin_info.version})"
        return plugin_info.version

    @classmethod
    def check_version_is_new(
        cls, plugin_info: StorePluginInfo, suc_plugin: dict[str, str]
    ):
        """检查版本是否有更新

        参数:
            plugin_info: StorePluginInfo
            suc_plugin: 模块名: 版本号

        返回:
            bool: 是否有更新
        """
        module = plugin_info.module
        return suc_plugin.get(module) and plugin_info.version == suc_plugin[module]

    @classmethod
    async def get_loaded_plugins(cls, *args) -> list[tuple[str, str]]:
        """获取已加载的插件

        返回:
            list[str]: 已加载的插件
        """
        return await PluginInfo.filter(load_status=True).values_list(*args)

    @classmethod
    async def get_plugins_info(cls) -> list[bytes] | str:
        """插件列表

        返回:
            bytes | str: 返回消息
        """
        plugin_list, extra_plugin_list = await cls.get_data()
        column_name = ["-", "ID", "名称", "简介", "作者", "版本", "类型"]
        db_plugin_list = await cls.get_loaded_plugins("module", "version")
        suc_plugin = {p[0]: (p[1] or "0.1") for p in db_plugin_list}

        HIGHLIGHT_COLOR = "#E6A23C"

        structured_native_list = []
        structured_extra_list = []
        index = 0

        for plugin_info in plugin_list:
            is_new = cls.check_version_is_new(plugin_info, suc_plugin)
            structured_native_list.append(
                {
                    "is_installed": plugin_info.module in suc_plugin,
                    "id": index,
                    "name": plugin_info.name,
                    "description": plugin_info.description,
                    "author": plugin_info.author,
                    "version_str": cls.version_check(plugin_info, suc_plugin),
                    "type_name": plugin_info.plugin_type_name,
                    "has_update": not is_new and plugin_info.module in suc_plugin,
                }
            )
            index += 1

        for plugin_info in extra_plugin_list:
            is_new = cls.check_version_is_new(plugin_info, suc_plugin)
            structured_extra_list.append(
                {
                    "is_installed": plugin_info.module in suc_plugin,
                    "id": index,
                    "name": plugin_info.name,
                    "description": plugin_info.description,
                    "author": plugin_info.author,
                    "version_str": cls.version_check(plugin_info, suc_plugin),
                    "type_name": plugin_info.plugin_type_name,
                    "has_update": not is_new and plugin_info.module in suc_plugin,
                }
            )
            index += 1

        native_table_builder = TableBuilder(
            title="原生插件列表", tip="通过添加/移除插件 ID 来管理插件"
        ).set_headers(column_name)

        native_rows_data = []
        for row_data in structured_native_list:
            row_color = HIGHLIGHT_COLOR if row_data["has_update"] else None
            status_cell = (
                StatusBadgeCell(text="已安装", status_type="ok")
                if row_data["is_installed"]
                else TextCell(content="")
            )
            native_rows_data.append(
                [
                    status_cell,
                    TextCell(content=str(row_data["id"]), color=row_color),
                    TextCell(content=row_data["name"], color=row_color),
                    TextCell(content=row_data["description"], color=row_color),
                    TextCell(content=row_data["author"], color=row_color),
                    TextCell(
                        content=row_data["version_str"],
                        color=row_color,
                        bold=bool(row_color),
                    ),
                    TextCell(content=row_data["type_name"], color=row_color),
                ]
            )
        native_table_builder.add_rows(native_rows_data)
        native_table_bytes = await ui.render(
            native_table_builder.build(),
            viewport={"width": 1400, "height": 10},
            device_scale_factor=2,
        )
        extra_table_builder = TableBuilder(
            title="第三方插件列表", tip="通过添加/移除插件 ID 来管理插件"
        ).set_headers(column_name)

        extra_rows_data = []
        for row_data in structured_extra_list:
            row_color = HIGHLIGHT_COLOR if row_data["has_update"] else None
            status_cell = (
                StatusBadgeCell(text="已安装", status_type="ok")
                if row_data["is_installed"]
                else TextCell(content="")
            )
            extra_rows_data.append(
                [
                    status_cell,
                    TextCell(content=str(row_data["id"]), color=row_color),
                    TextCell(content=row_data["name"], color=row_color),
                    TextCell(content=row_data["description"], color=row_color),
                    TextCell(content=row_data["author"], color=row_color),
                    TextCell(
                        content=row_data["version_str"],
                        color=row_color,
                        bold=bool(row_color),
                    ),
                    TextCell(content=row_data["type_name"], color=row_color),
                ]
            )
        extra_table_builder.add_rows(extra_rows_data)
        extra_table_bytes = await ui.render(
            extra_table_builder.build(),
            viewport={"width": 1400, "height": 10},
            device_scale_factor=2,
        )

        return [native_table_bytes, extra_table_bytes]

    @classmethod
    async def get_plugin_by_value(
        cls,
        index_or_module: str,
        is_update: bool = False,
        is_remove: bool = False,
    ) -> tuple[StorePluginInfo, bool]:
        """获取插件信息

        参数:
            index_or_module: 插件索引或模块名
            is_update: 是否是更新插件
            is_remove: 是否是移除插件

        异常:
            PluginStoreException: 插件不存在
            PluginStoreException: 插件已安装

        返回:
            StorePluginInfo: 插件信息
            bool: 是否是外部插件
        """
        plugin_list, extra_plugin_list = await cls.get_data()
        plugin_info = None
        is_external = False
        db_plugin_list = await cls.get_loaded_plugins("module")
        plugin_key = await cls._resolve_plugin_key(index_or_module)
        for p in plugin_list:
            if p.module == plugin_key:
                is_external = False
                plugin_info = p
                break
        for p in extra_plugin_list:
            if p.module == plugin_key:
                is_external = True
                plugin_info = p
                break
        if not plugin_info:
            raise PluginStoreException(f"插件不存在: {plugin_key}")

        modules = [p[0] for p in db_plugin_list]

        if is_remove:
            if plugin_info.module not in modules:
                raise PluginStoreException(f"插件 {plugin_info.name} 未安装，无法移除")
            return plugin_info, is_external

        if is_update:
            if plugin_info.module not in modules:
                raise PluginStoreException(f"插件 {plugin_info.name} 未安装，无法更新")
            return plugin_info, is_external

        if plugin_info.module in modules:
            raise PluginStoreException(f"插件 {plugin_info.name} 已安装，无需重复安装")

        return plugin_info, is_external

    @classmethod
    async def add_plugin(cls, index_or_module: str) -> str:
        """添加插件

        参数:
            plugin_id: 插件id或模块名

        返回:
            str: 返回消息
        """
        plugin_info, is_external = await cls.get_plugin_by_value(index_or_module)
        if plugin_info.github_url is None:
            plugin_info.github_url = DEFAULT_GITHUB_URL
        version_split = plugin_info.version.split("-")
        if len(version_split) > 1:
            github_url_split = plugin_info.github_url.split("/tree/")
            plugin_info.github_url = f"{github_url_split[0]}/tree/{version_split[1]}"
        logger.info(f"正在安装插件 {plugin_info.name}...", LOG_COMMAND)
        await cls.install_plugin_with_repo(
            plugin_info.github_url,
            plugin_info.module_path,
            plugin_info.is_dir,
            is_external,
        )
        return f"插件 {plugin_info.name} 安装成功! 重启后生效"

    @classmethod
    async def install_plugin_with_repo(
        cls,
        github_url: str,
        module_path: str,
        is_dir: bool,
        is_external: bool = False,
    ):
        """安装插件

        参数:
            github_url: 仓库地址
            module_path: 模块路径
            is_dir: 是否是文件夹
            is_external: 是否是外部仓库
        """
        repo_type = RepoType.GITHUB if is_external else None
        replace_module_path = module_path.replace(".", "/")
        if is_dir:
            files = await RepoFileManager.list_directory_files(
                github_url, replace_module_path, repo_type=repo_type
            )
        else:
            files = [RepoFileInfo(path=f"{replace_module_path}.py", is_dir=False)]
        local_path = BASE_PATH / "plugins" if is_external else BASE_PATH
        files = [file for file in files if not file.is_dir]
        download_files = [(file.path, local_path / file.path) for file in files]
        await RepoFileManager.download_files(
            github_url, download_files, repo_type=repo_type
        )

        requirement_paths = [
            file
            for file in files
            if file.path.endswith("requirement.txt")
            or file.path.endswith("requirements.txt")
        ]

        is_install_req = False
        for requirement_path in requirement_paths:
            requirement_file = local_path / requirement_path.path
            if requirement_file.exists():
                is_install_req = True
                await VirtualEnvPackageManager.install_requirement(requirement_file)

        if not is_install_req:
            rand = random.randint(1, 10000)
            requirement_path = TEMP_PATH / f"plugin_store_{rand}_req.txt"
            requirements_path = TEMP_PATH / f"plugin_store_{rand}_reqs.txt"
            await RepoFileManager.download_files(
                github_url,
                [
                    ("requirement.txt", requirement_path),
                    ("requirements.txt", requirements_path),
                ],
                repo_type=repo_type,
                ignore_error=True,
            )
            if requirement_path.exists():
                logger.info(
                    f"开始安装插件 {module_path} 依赖文件: {requirement_path}",
                    LOG_COMMAND,
                )
                await VirtualEnvPackageManager.install_requirement(requirement_path)
            if requirements_path.exists():
                logger.info(
                    f"开始安装插件 {module_path} 依赖文件: {requirements_path}",
                    LOG_COMMAND,
                )
                await VirtualEnvPackageManager.install_requirement(requirements_path)

    @classmethod
    async def remove_plugin(cls, index_or_module: str) -> str:
        """移除插件

        参数:
            index_or_module: 插件id或模块名

        返回:
            str: 返回消息
        """
        plugin_info, _ = await cls.get_plugin_by_value(index_or_module, is_remove=True)
        path = BASE_PATH
        if plugin_info.github_url:
            path = BASE_PATH / "plugins"
        for p in plugin_info.module_path.split("."):
            path = path / p
        if not plugin_info.is_dir:
            path = Path(f"{path}.py")
        if not path.exists():
            return f"插件 {plugin_info.name} 不存在..."
        logger.debug(f"尝试移除插件 {plugin_info.name} 文件: {path}", LOG_COMMAND)
        if plugin_info.is_dir:
            shutil.rmtree(path)
        else:
            path.unlink()
        await PluginInitManager.remove(f"zhenxun.{plugin_info.module_path}")
        return f"插件 {plugin_info.name} 移除成功! 重启后生效"

    @classmethod
    async def search_plugin(cls, plugin_name_or_author: str) -> bytes | str:
        """搜索插件

        参数:
            plugin_name_or_author: 插件名称或作者

        返回:
            bytes | str: 返回消息
        """
        plugin_list, extra_plugin_list = await cls.get_data()
        all_plugin_list = plugin_list + extra_plugin_list
        db_plugin_list = await cls.get_loaded_plugins("module", "version")
        suc_plugin = {p[0]: (p[1] or "Unknown") for p in db_plugin_list}

        filtered_data = [
            (id, plugin_info)
            for id, plugin_info in enumerate(all_plugin_list)
            if plugin_name_or_author.lower() in plugin_info.name.lower()
            or plugin_name_or_author.lower() in plugin_info.author.lower()
        ]

        if not filtered_data:
            return "未找到相关插件..."

        HIGHLIGHT_COLOR = "#E6A23C"
        column_name = ["-", "ID", "名称", "简介", "作者", "版本", "类型"]

        builder = TableBuilder(
            title=f"插件搜索结果: '{plugin_name_or_author}'",
            tip="通过添加/移除插件 ID 来管理插件",
        )
        builder.set_headers(column_name)

        rows_to_add = []
        for id, plugin_info in filtered_data:
            is_new = cls.check_version_is_new(plugin_info, suc_plugin)
            has_update = not is_new and plugin_info.module in suc_plugin
            row_color = HIGHLIGHT_COLOR if has_update else None

            status_cell = (
                StatusBadgeCell(text="已安装", status_type="ok")
                if plugin_info.module in suc_plugin
                else TextCell(content="")
            )

            rows_to_add.append(
                [
                    status_cell,
                    TextCell(content=str(id), color=row_color),
                    TextCell(content=plugin_info.name, color=row_color),
                    TextCell(content=plugin_info.description, color=row_color),
                    TextCell(content=plugin_info.author, color=row_color),
                    TextCell(
                        content=cls.version_check(plugin_info, suc_plugin),
                        color=row_color,
                        bold=has_update,
                    ),
                    TextCell(content=plugin_info.plugin_type_name, color=row_color),
                ]
            )

        builder.add_rows(rows_to_add)

        render_viewport = {"width": 1400, "height": 10}
        return await ui.render(builder.build(), viewport=render_viewport)

    @classmethod
    async def update_plugin(cls, index_or_module: str) -> str:
        """更新插件

        参数:
            index_or_module: 插件id

        返回:
            str: 返回消息
        """
        plugin_info, is_external = await cls.get_plugin_by_value(index_or_module, True)
        logger.info(f"尝试更新插件 {plugin_info.name}", LOG_COMMAND)
        db_plugin_list = await cls.get_loaded_plugins("module", "version")
        suc_plugin = {p[0]: (p[1] or "Unknown") for p in db_plugin_list}
        logger.debug(f"当前插件列表: {suc_plugin}", LOG_COMMAND)
        if cls.check_version_is_new(plugin_info, suc_plugin):
            return f"插件 {plugin_info.name} 已是最新版本"
        if plugin_info.github_url is None:
            plugin_info.github_url = DEFAULT_GITHUB_URL
        await cls.install_plugin_with_repo(
            plugin_info.github_url,
            plugin_info.module_path,
            plugin_info.is_dir,
            is_external,
        )
        return f"插件 {plugin_info.name} 更新成功! 重启后生效"

    @classmethod
    async def update_all_plugin(cls) -> str:
        """更新插件

        参数:
            plugin_id: 插件id

        返回:
            str: 返回消息
        """
        plugin_list, extra_plugin_list = await cls.get_data()
        all_plugin_list = plugin_list + extra_plugin_list
        plugin_name_list = [p.name for p in all_plugin_list]
        update_failed_list = []
        update_success_list = []
        result = "--已更新{}个插件 {}个失败 {}个成功--"
        logger.info(f"尝试更新全部插件 {plugin_name_list}", LOG_COMMAND)
        for plugin_info in all_plugin_list:
            try:
                db_plugin_list = await cls.get_loaded_plugins("module", "version")
                suc_plugin = {p[0]: (p[1] or "Unknown") for p in db_plugin_list}
                if plugin_info.module not in [p[0] for p in db_plugin_list]:
                    logger.debug(
                        f"插件 {plugin_info.name}({plugin_info.module}) 未安装，跳过",
                        LOG_COMMAND,
                    )
                    continue
                if cls.check_version_is_new(plugin_info, suc_plugin):
                    logger.debug(
                        f"插件 {plugin_info.name}({plugin_info.module}) "
                        "已是最新版本，跳过",
                        LOG_COMMAND,
                    )
                    continue
                logger.info(
                    f"正在更新插件 {plugin_info.name}({plugin_info.module})",
                    LOG_COMMAND,
                )
                is_external = True
                if plugin_info.github_url is None:
                    plugin_info.github_url = DEFAULT_GITHUB_URL
                    is_external = False
                await cls.install_plugin_with_repo(
                    plugin_info.github_url,
                    plugin_info.module_path,
                    plugin_info.is_dir,
                    is_external,
                )
                update_success_list.append(plugin_info.name)
            except Exception as e:
                logger.error(
                    f"更新插件 {plugin_info.name}({plugin_info.module}) 失败",
                    LOG_COMMAND,
                    e=e,
                )
                update_failed_list.append(plugin_info.name)
        if not update_success_list and not update_failed_list:
            return "全部插件已是最新版本"
        if update_success_list:
            result += "\n* 以下插件更新成功:\n\t- {}".format(
                "\n\t- ".join(update_success_list)
            )
        if update_failed_list:
            result += "\n* 以下插件更新失败:\n\t- {}".format(
                "\n\t- ".join(update_failed_list)
            )
        return (
            result.format(
                len(update_success_list) + len(update_failed_list),
                len(update_failed_list),
                len(update_success_list),
            )
            + "\n重启后生效"
        )

    @classmethod
    async def _resolve_plugin_key(cls, plugin_id: str) -> str:
        """获取插件module

        参数:
            plugin_id: module，id或插件名称

        异常:
            PluginStoreException: 插件不存在
            PluginStoreException: 插件不存在

        返回:
            str: 插件模块名
        """
        plugin_list, extra_plugin_list = await cls.get_data()
        all_plugin_list = plugin_list + extra_plugin_list
        if is_number(plugin_id):
            idx = int(plugin_id)
            if idx < 0 or idx >= len(all_plugin_list):
                raise PluginStoreException("插件ID不存在...")
            return all_plugin_list[idx].module
        elif isinstance(plugin_id, str):
            result = (
                None
                if plugin_id not in [v.module for v in all_plugin_list]
                else plugin_id
            ) or next(v for v in all_plugin_list if v.name == plugin_id).module
            if not result:
                raise PluginStoreException("插件 Module / 名称 不存在...")
            return result
