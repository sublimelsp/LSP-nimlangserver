from __future__ import annotations

import os
import shutil
import stat
import subprocess
import urllib.request

import sublime
from LSP.plugin import ClientConfig
from LSP.plugin import LspPlugin
from LSP.plugin import OnPreStartContext
from LSP.plugin import PluginStartError

VERSION = "1.16.0"
"""
Update this single git tag to download a newer version.
After changing this tag, go through the server settings again to see
if any new server settings are added or old ones removed.
"""
SETTINGS_FILENAME = "LSP-nimlangserver.sublime-settings"
# https://github.com/nim-lang/langserver/releases/download/v1.10.0/nimlangserver-windows-amd64.zip
URL = "https://github.com/nim-lang/langserver/releases/download/v{tag}/nimlangserver-{platform}-{arch}.{archive_type}"


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


def set_setting_and_save(key: str, value: str) -> None:
    settings = sublime.load_settings(SETTINGS_FILENAME)
    settings.set(key, value)
    return sublime.save_settings(SETTINGS_FILENAME)


def project_lsp_settings(window: sublime.Window | None, config_name: str) -> tuple[dict, dict] | None:
    """Returns the project data and the config overrides within it, if the project defines any."""
    project_data = window.project_data() if window else None
    if not isinstance(project_data, dict):
        return None
    settings = project_data.get("settings")
    lsp_settings = settings.get("LSP") if isinstance(settings, dict) else None
    overrides = lsp_settings.get(config_name) if isinstance(lsp_settings, dict) else None
    return (project_data, overrides) if isinstance(overrides, dict) else None


def get_project_lsp_setting(window: sublime.Window | None, config_name: str, key: str) -> bool:
    project_settings = project_lsp_settings(window, config_name)
    return project_settings is not None and key in project_settings[1]


def set_project_lsp_setting_and_save(window: sublime.Window, config_name: str, key: str, value: str) -> None:
    project_settings = project_lsp_settings(window, config_name)
    if project_settings is None:
        return
    project_data, overrides = project_settings
    overrides[key] = value
    window.set_project_data(project_data)


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


class NimlangserverPlugin(LspPlugin):
    @classmethod
    def on_pre_start_async(cls, context: OnPreStartContext) -> None:
        configuration = context.configuration
        if cls.needs_update_or_installation(configuration):
            cls.install_or_update(configuration, context.view.window())
        binary_setting = cls.binary_setting(configuration)
        if binary_setting:
            path = cls.system_server_path(binary_setting)
            if path and cls.get_server_version(path) < (1, 2, 0):
                raise PluginStartError("The minimum required nimlangserver version (1.2.0) is not satisfied.")
        path = shutil.which("nim")
        if path is None or not os.path.isfile(path):
            raise PluginStartError("Nim is not in PATH.")
        server_path = cls.server_path(configuration)
        if not server_path:
            raise PluginStartError("nimlangserver is currently not installed.")
        configuration.command = [server_path]

    @classmethod
    def binary_setting(cls, configuration: ClientConfig) -> str:
        """The "binary" setting: the nimlangserver to use, or empty to download it."""
        binary = configuration.root_settings.get("binary")
        return binary if isinstance(binary, str) else ""

    @classmethod
    def storage_path(cls) -> str:
        """${storage_path}/LSP-nimlangserver"""
        return str(cls.plugin_storage_path)

    @classmethod
    def get_server_version(cls, path: str) -> tuple[int, int, int]:
        with subprocess.Popen([path, "-v"], stdout=subprocess.PIPE, shell=os.name == "nt") as process:
            stdout, _ = process.communicate(timeout=5)

            if process.returncode == 0:
                v = [int(s) for s in stdout.split(b".")]
                return (v[0], v[1], v[2])
            else:
                return (0, 0, 0)

    @classmethod
    def managed_server_path(cls) -> str | None:
        binary_name = "nimlangserver.exe" if sublime.platform() == "windows" else "nimlangserver"
        path = os.path.join(cls.storage_path(), binary_name)
        if os.path.exists(path):
            return path
        return None

    @classmethod
    def system_server_path(cls, binary: str) -> str | None:
        binary_path = shutil.which(binary) or binary
        if not os.path.isfile(binary_path):
            return None
        return binary_path

    @classmethod
    def server_path(cls, configuration: ClientConfig) -> str | None:
        """The command to start the server."""
        binary_setting = cls.binary_setting(configuration)
        if binary_setting:
            return cls.system_server_path(binary_setting)
        else:
            return cls.managed_server_path()

    @classmethod
    def needs_update_or_installation(cls, configuration: ClientConfig) -> bool:
        path = cls.server_path(configuration)
        version_tuple = tuple(int(n) for n in VERSION.split('.'))
        return not path or cls.get_server_version(path) < version_tuple

    @classmethod
    def install_or_update(cls, configuration: ClientConfig, window: sublime.Window | None) -> None:
        binary_setting = cls.binary_setting(configuration)
        if binary_setting:
            if cls.system_server_path(binary_setting):
                msg = "A newer version of nimlangserver is available."
            else:
                msg = "nimlangserver was not found in your PATH."
            in_project = get_project_lsp_setting(window, configuration.name, "binary")
            settings_location = "project settings" if in_project else f"{cls.name} settings"
            answer = sublime.ok_cancel_dialog(
                f"{msg} Would you like to auto-install nimlangserver from GitHub?\n\n"
                f"The \"binary\" setting will be changed to \"\" in the {settings_location}.",
                ok_title="Install")
            if not answer:
                # Keep using the configured nimlangserver, if there is one.
                return
            if window and in_project:
                set_project_lsp_setting_and_save(window, configuration.name, "binary", "")
            else:
                set_setting_and_save("binary", "")
            # Use the downloaded server for this start already.
            configuration.root_settings["binary"] = ""
        try:
            if os.path.isdir(cls.storage_path()):
                shutil.rmtree(cls.storage_path())
            os.makedirs(cls.storage_path(), exist_ok=True)

            archive_type = "tar.gz" if sublime.platform() == "linux" else "zip"
            archive_file = os.path.join(cls.storage_path(), "nimlangserver." + archive_type)
            url = URL.format(tag=VERSION, arch=arch(), platform=platform(), archive_type=archive_type)

            sublime.status_message(cls.name + ": Downloading server...")
            download_server(url, archive_file)

            sublime.status_message(cls.name + ": Extracting server...")
            extract_server(archive_file, cls.storage_path())

            os.remove(archive_file)

            path = cls.managed_server_path()
            if not path:
                raise ValueError("installation failed.")
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
        except BaseException:
            shutil.rmtree(cls.storage_path(), ignore_errors=True)
            raise


def plugin_loaded() -> None:
    NimlangserverPlugin.register()


def plugin_unloaded() -> None:
    NimlangserverPlugin.unregister()
