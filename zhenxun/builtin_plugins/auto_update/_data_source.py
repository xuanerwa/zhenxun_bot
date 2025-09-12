import asyncio
from typing import Literal

from nonebot.adapters import Bot
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.manager.virtual_env_package_manager import VirtualEnvPackageManager
from zhenxun.utils.manager.zhenxun_repo_manager import (
    ZhenxunRepoConfig,
    ZhenxunRepoManager,
)
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.repo_utils import RepoFileManager

LOG_COMMAND = "AutoUpdate"


class UpdateManager:
    @staticmethod
    async def _get_latest_commit_date(owner: str, repo: str, path: str) -> str:
        """获取文件最新 commit 日期"""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {"path": path, "page": 1, "per_page": 1}
        try:
            data = await AsyncHttpx.get_json(api_url, params=params)
            if data and isinstance(data, list) and data[0]:
                date_str = data[0]["commit"]["committer"]["date"]
                return date_str.split("T")[0]
        except Exception as e:
            logger.warning(f"获取 {owner}/{repo}/{path} 的 commit 日期失败", e=e)
        return "获取失败"

    @classmethod
    async def check_version(cls) -> str:
        """检查真寻和资源的版本"""
        bot_cur_version = cls.__get_version()

        release_task = ZhenxunRepoManager.zhenxun_get_latest_releases_data()
        dev_version_task = RepoFileManager.get_file_content(
            ZhenxunRepoConfig.ZHENXUN_BOT_GITHUB_URL, "__version__"
        )
        bot_commit_date_task = cls._get_latest_commit_date(
            "HibiKier", "zhenxun_bot", "__version__"
        )
        res_commit_date_task = cls._get_latest_commit_date(
            "zhenxun-org", "zhenxun-bot-resources", "__version__"
        )

        (
            release_data,
            dev_version_text,
            bot_commit_date,
            res_commit_date,
        ) = await asyncio.gather(
            release_task,
            dev_version_task,
            bot_commit_date_task,
            res_commit_date_task,
            return_exceptions=True,
        )

        if isinstance(release_data, dict):
            bot_release_version = release_data.get("name", "获取失败")
            bot_release_date = release_data.get("created_at", "").split("T")[0]
        else:
            bot_release_version = "获取失败"
            bot_release_date = "获取失败"
            logger.warning(f"获取 Bot release 信息失败: {release_data}")

        if isinstance(dev_version_text, str):
            bot_dev_version = dev_version_text.split(":")[-1].strip()
        else:
            bot_dev_version = "获取失败"
            bot_commit_date = "获取失败"
            logger.warning(f"获取 Bot dev 版本信息失败: {dev_version_text}")

        bot_update_hint = ""
        try:
            cur_base_v = bot_cur_version.split("-")[0].lstrip("v")
            dev_base_v = bot_dev_version.split("-")[0].lstrip("v")

            if Version(cur_base_v) < Version(dev_base_v):
                bot_update_hint = "\n-> 发现新开发版本, 可用 `检查更新 main` 更新"
            elif (
                Version(cur_base_v) == Version(dev_base_v)
                and bot_cur_version != bot_dev_version
            ):
                bot_update_hint = "\n-> 发现新开发版本, 可用 `检查更新 main` 更新"
        except (InvalidVersion, TypeError, IndexError):
            if bot_cur_version != bot_dev_version and bot_dev_version != "获取失败":
                bot_update_hint = "\n-> 发现新开发版本, 可用 `检查更新 main` 更新"

        bot_update_info = (
            f"当前版本: {bot_cur_version}\n"
            f"最新开发版: {bot_dev_version} (更新于: {bot_commit_date})\n"
            f"最新正式版: {bot_release_version} (发布于: {bot_release_date})"
            f"{bot_update_hint}"
        )

        res_version_file = ZhenxunRepoConfig.RESOURCE_PATH / "__version__"
        res_cur_version = "未找到"
        if res_version_file.exists():
            if text := res_version_file.open(encoding="utf8").readline():
                res_cur_version = text.split(":")[-1].strip()

        res_latest_version = "获取失败"
        try:
            res_latest_version_text = await RepoFileManager.get_file_content(
                ZhenxunRepoConfig.RESOURCE_GITHUB_URL, "__version__"
            )
            res_latest_version = res_latest_version_text.split(":")[-1].strip()
        except Exception as e:
            res_commit_date = "获取失败"
            logger.warning(f"获取资源版本信息失败: {e}")

        res_update_hint = ""
        try:
            if Version(res_cur_version) < Version(res_latest_version):
                res_update_hint = "\n-> 发现新资源版本, 可用 `检查更新 resource` 更新"
        except (InvalidVersion, TypeError):
            pass

        res_update_info = (
            f"当前版本: {res_cur_version}\n"
            f"最新版本: {res_latest_version} (更新于: {res_commit_date})"
            f"{res_update_hint}"
        )

        return f"『绪山真寻 Bot』\n{bot_update_info}\n\n『真寻资源』\n{res_update_info}"

    @classmethod
    async def update_webui(
        cls,
        source: Literal["git", "ali"] | None,
        branch: str = "dist",
        force: bool = False,
    ):
        """更新WebUI

        参数:
            source: 更新源
            branch: 分支
            force: 是否强制更新

        返回:
            str: 返回消息
        """
        if not source:
            await ZhenxunRepoManager.webui_zip_update()
            return "WebUI更新完成!"
        result = await ZhenxunRepoManager.webui_git_update(
            source,
            branch=branch,
            force=force,
        )
        if not result.success:
            logger.error(f"WebUI更新失败...错误: {result.error_message}", LOG_COMMAND)
            return f"WebUI更新失败...错误: {result.error_message}"
        return "WebUI更新完成!"

    @classmethod
    async def update_resources(
        cls,
        source: Literal["git", "ali"] | None,
        branch: str = "main",
        force: bool = False,
    ) -> str:
        """更新资源

        参数:
            source: 更新源
            branch: 分支
            force: 是否强制更新

        返回:
            str: 返回消息
        """
        if not source:
            await ZhenxunRepoManager.resources_zip_update()
            return "真寻资源更新完成!"
        result = await ZhenxunRepoManager.resources_git_update(
            source,
            branch=branch,
            force=force,
        )
        if not result.success:
            logger.error(
                f"真寻资源更新失败...错误: {result.error_message}", LOG_COMMAND
            )
            return f"真寻资源更新失败...错误: {result.error_message}"
        return "真寻资源更新完成!"

    @classmethod
    async def update_zhenxun(
        cls,
        bot: Bot,
        user_id: str,
        version_type: Literal["main", "release"],
        force: bool,
        source: Literal["git", "ali"],
        zip: bool,
    ) -> str:
        """更新操作

        参数:
            bot: Bot
            user_id: 用户id
            version_type: 更新版本类型
            force: 是否强制更新
            source: 更新源
            zip: 是否下载zip文件
            update_type: 更新方式

        返回:
            str | None: 返回消息
        """
        cur_version = cls.__get_version()
        await PlatformUtils.send_superuser(
            bot,
            f"检测真寻已更新，当前版本：{cur_version}\n开始更新...",
            user_id,
        )
        result_message = ""
        if zip:
            new_version = await ZhenxunRepoManager.zhenxun_zip_update(version_type)
            await PlatformUtils.send_superuser(
                bot, "真寻更新完成，开始安装依赖...", user_id
            )
            await VirtualEnvPackageManager.install_requirement(
                ZhenxunRepoConfig.REQUIREMENTS_FILE
            )
            result_message = (
                f"版本更新完成！\n版本: {cur_version} -> {new_version}\n"
                "请重新启动真寻以完成更新!"
            )
        else:
            result = await ZhenxunRepoManager.zhenxun_git_update(
                source,
                branch=version_type,
                force=force,
            )
            if not result.success:
                logger.error(
                    f"真寻版本更新失败...错误: {result.error_message}",
                    LOG_COMMAND,
                )
                return f"版本更新失败...错误: {result.error_message}"
            await PlatformUtils.send_superuser(
                bot, "真寻更新完成，开始安装依赖...", user_id
            )
            await VirtualEnvPackageManager.install_requirement(
                ZhenxunRepoConfig.REQUIREMENTS_FILE
            )
            result_message = (
                f"版本更新完成！\n"
                f"版本: {cur_version} -> {result.new_version}\n"
                f"变更文件个数: {len(result.changed_files)}"
                f"{'' if source == 'git' else '（阿里云更新不支持查看变更文件）'}\n"
                "请重新启动真寻以完成更新!"
            )
        resource_warning = ""
        if version_type == "main":
            try:
                spec_content = await RepoFileManager.get_file_content(
                    ZhenxunRepoConfig.ZHENXUN_BOT_GITHUB_URL, "resources.spec"
                )
                required_spec_str = None
                for line in spec_content.splitlines():
                    if line.startswith("require_resources_version:"):
                        required_spec_str = line.split(":", 1)[1].strip().strip("\"'")
                        break
                if required_spec_str:
                    res_version_file = ZhenxunRepoConfig.RESOURCE_PATH / "__version__"
                    local_res_version_str = "0.0.0"
                    if res_version_file.exists():
                        if text := res_version_file.open(encoding="utf8").readline():
                            local_res_version_str = text.split(":")[-1].strip()

                    spec = SpecifierSet(required_spec_str)
                    local_ver = Version(local_res_version_str)
                    if not spec.contains(local_ver):
                        warning_header = (
                            f"⚠️ **资源版本不兼容!**\n"
                            f"当前代码需要资源版本: `{required_spec_str}`\n"
                            f"您当前的资源版本是: `{local_res_version_str}`\n"
                            "**将自动为您更新资源文件...**"
                        )
                        await PlatformUtils.send_superuser(bot, warning_header, user_id)
                        resource_update_source = None if zip else source
                        resource_update_result = await cls.update_resources(
                            source=resource_update_source, force=force
                        )
                        resource_warning = (
                            f"\n\n{warning_header}\n{resource_update_result}"
                        )
            except Exception as e:
                logger.warning(f"检查资源版本兼容性时出错: {e}", LOG_COMMAND, e=e)
                resource_warning = (
                    "\n\n⚠️ 检查资源版本兼容性时出错，建议手动运行 `检查更新 resource`"
                )
        return result_message + resource_warning

    @classmethod
    def __get_version(cls) -> str:
        """获取当前版本

        返回:
            str: 当前版本号
        """
        _version = "v0.0.0"
        if ZhenxunRepoConfig.ZHENXUN_BOT_VERSION_FILE.exists():
            if text := ZhenxunRepoConfig.ZHENXUN_BOT_VERSION_FILE.open(
                encoding="utf8"
            ).readline():
                _version = text.split(":")[-1].strip()
        return _version
