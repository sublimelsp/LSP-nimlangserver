import os
import shutil
import stat
import subprocess
import urllib.request

import sublime
from LSP.plugin import AbstractPlugin
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin.core.types import ClientConfig
from LSP.plugin.core.typing import List, Optional, Tuple
from LSP.plugin.core.views import MarkdownLangMap
from LSP.plugin.core.workspace import WorkspaceFolder



VERSION = (1, 2, 0)
"""
Update this single git tag to download a newer version.
After changing this tag, go through the server settings again to see
if any new server settings are added or old ones removed.
"""
SESSION_NAME = "nimlangserver"
SETTINGS_FILENAME = "LSP-nimlangserver.sublime-settings"
# https://github.com/nim-lang/langserver/releases/download/v1.2.0/nimlangserver-1.2.0-windows-amd64.zip
URL = "https://github.com/nim-lang/langserver/releases/download/v{tag}/nimlangserver-{tag}-{platform}-{arch}.{archive_type}"


def arch() -> str:
    if sublime.arch() == "x64":
        return "amd64"
    elif sublime.arch() == "x32":
        raise RuntimeError("Unsupported architecture: 32-bit is not supported")
    elif sublime.arch() == "arm64":
        return "arm64"
    else:
        raise RuntimeError("Unknown architecture: " + sublime.arch())


def platform() -> str:
    return "macos" if sublime.platform() == "osx" else sublime.platform()


def get_settings() -> sublime.Settings:
    return sublime.load_settings(SETTINGS_FILENAME)


def save_settings() -> None:
    return sublime.save_settings(SETTINGS_FILENAME)


def download_server(url: str, file: str) -> None:
    with urllib.request.urlopen(url) as response, open(file, "wb") as out_file:
        shutil.copyfileobj(response, out_file)


def extract_server(archive_file: str, out_dir: str) -> None:
    if archive_file.endswith("zip"):
        import zipfile

        with zipfile.ZipFile(archive_file) as archive:
            archive.extractall(out_dir)
    else:
        import tarfile

        with tarfile.TarFile.open(archive_file) as archive:
            archive.extractall(out_dir)


class NimlangserverPlugin(AbstractPlugin):
    @classmethod
    def name(cls) -> str:
        return SESSION_NAME

    @classmethod
    def markdown_language_id_to_st_syntax_map(cls) -> Optional[MarkdownLangMap]:
        path = sublime.find_syntax_by_name("Nim")[0].path
        return {"nim": (("nim",), (path[9 : path.rfind(".")],))}

    @classmethod
    def basedir(cls) -> str:
        """${storage_path}/LSP-nimlangserver"""
        return os.path.join(cls.storage_path(), __package__ or "")

    @classmethod
    def get_server_version(cls, path: str) -> Tuple[int, int, int]:
        with subprocess.Popen([path, "-v"], stdout=subprocess.PIPE, shell=os.name == "nt") as process:
            stdout, _ = process.communicate(timeout=5)

            if process.returncode == 0:
                v = [int(s) for s in stdout.split(b".")]
                return (v[0], v[1], v[2])
            else:
                return (0, 0, 0)

    @classmethod
    def managed_server_path(cls) -> Optional[str]:
        binary_name = "nimlangserver.exe" if sublime.platform() == "windows" else "nimlangserver"
        path = os.path.join(cls.basedir(), binary_name)
        if os.path.exists(path):
            return path
        return None

    @classmethod
    def system_server_path(cls, binary: str) -> Optional[str]:
        binary_path = shutil.which(binary) or binary
        if not os.path.isfile(binary_path):
            return None
        return binary_path

    @classmethod
    def server_path(cls) -> Optional[str]:
        """The command to start the server."""
        binary_setting = get_settings().get("binary")
        if binary_setting and isinstance(binary_setting, str):
            return cls.system_server_path(binary_setting)
        else:
            return cls.managed_server_path()

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        path = cls.server_path()
        return not path or cls.get_server_version(path) < VERSION

    @classmethod
    def install_or_update(cls) -> None:
        binary_setting = get_settings().get("binary")
        if binary_setting and isinstance(binary_setting, str):
            path = cls.system_server_path(binary_setting)
            if path:
                msg = "A newer version of nimlangserver exists."
            else:
                msg = "nimlangserver was not found in your path."
            ans = sublime.ok_cancel_dialog(
                msg + " Would you like to auto-install it from Github ?", "Yes", "LSP-nimlangserver"
            )
            if ans == sublime.DIALOG_YES:
                get_settings().set("binary", "")
                save_settings()
            else:
                return
        try:
            if os.path.isdir(cls.basedir()):
                shutil.rmtree(cls.basedir())
            os.makedirs(cls.basedir(), exist_ok=True)

            archive_type = "tar.gz" if sublime.platform() == "linux" else "zip"
            archive_file = os.path.join(cls.basedir(), "nimlangserver." + archive_type)
            version_str = ".".join(str(i) for i in VERSION)
            url = URL.format(tag=version_str, arch=arch(), platform=platform(), archive_type=archive_type)

            sublime.status_message(SESSION_NAME + ": Downloading server...")
            download_server(url, archive_file)

            sublime.status_message(SESSION_NAME + ": Extracting server...")
            extract_server(archive_file, cls.basedir())

            os.remove(archive_file)

            path = cls.managed_server_path()
            if not path:
                raise ValueError("installation failed.")
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        except BaseException:
            shutil.rmtree(cls.basedir(), ignore_errors=True)
            raise

    @classmethod
    def can_start(
        cls,
        window: sublime.Window,
        initiating_view: sublime.View,
        workspace_folders: List[WorkspaceFolder],
        configuration: ClientConfig,
    ) -> Optional[str]:
        binary_setting = get_settings().get("binary")
        if binary_setting and isinstance(binary_setting, str):
            path = cls.system_server_path(binary_setting)
            if path and cls.get_server_version(path) < (1, 2, 0):
                return "The minimum required nimlangserver version (1.2.0) is not satisfied."
        path = shutil.which("nim")
        if path is None or not os.path.isfile(path):
            return "Nim is not in PATH."

    @classmethod
    def on_pre_start(
        cls,
        window: sublime.Window,
        initiating_view: sublime.View,
        workspace_folders: List[WorkspaceFolder],
        configuration: ClientConfig,
    ) -> Optional[str]:
        server_path = cls.server_path()
        if not server_path:
            raise ValueError("nimlangserver is currently not installed.")
        configuration.command = [server_path]


def plugin_loaded() -> None:
    register_plugin(NimlangserverPlugin)


def plugin_unloaded() -> None:
    unregister_plugin(NimlangserverPlugin)
