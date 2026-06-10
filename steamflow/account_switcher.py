import subprocess
import sys
import time
from pathlib import Path

from .os_integration import build_hidden_process_kwargs, build_hidden_run_kwargs, open_uri, start_hidden_process

try:
    import winreg
except ImportError:
    import _winreg as winreg


STEAM_PROCESS_IMAGE_NAMES = (
    "steam.exe",
    "steamwebhelper.exe",
    "GameOverlayUI.exe",
    "steamservice.exe",
)


def set_steam_registry_autologin_user(account_name, registry=winreg, flush=False):
    with registry.CreateKey(registry.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        registry.SetValueEx(key, "AutoLoginUser", 0, registry.REG_SZ, str(account_name or ""))
        registry.SetValueEx(key, "RememberPassword", 0, registry.REG_DWORD, 1)
        if flush:
            registry.FlushKey(key)


def read_active_steam_user_id_from_registry(registry=winreg):
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam\ActiveProcess") as key:
            active_user, _ = registry.QueryValueEx(key, "ActiveUser")
        active_user = str(active_user).strip()
        if active_user and active_user != "0":
            return active_user
    except Exception:
        pass
    return None


def is_windows_process_running(
    image_name,
    runner=subprocess.run,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    result = runner(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
        capture_output=True,
        text=True,
        timeout=10,
        **build_hidden_run_kwargs(platform=platform, subprocess_module=subprocess_module),
    )
    combined_output = " ".join(filter(None, [result.stdout, result.stderr])).lower()
    return image_name.lower() in combined_output


def terminate_process_tree(image_name, runner=subprocess.run, process_running=is_windows_process_running):
    if not process_running(image_name):
        return
    result = runner(
        ["taskkill", "/F", "/T", "/IM", image_name],
        capture_output=True,
        text=True,
        timeout=20,
        **build_hidden_run_kwargs(),
    )
    output_text = " ".join(filter(None, [result.stdout, result.stderr])).strip()
    if process_running(image_name):
        raise RuntimeError(output_text or f"taskkill exited with code {result.returncode}")


def terminate_steam_processes(
    image_names=STEAM_PROCESS_IMAGE_NAMES,
    process_running=is_windows_process_running,
    runner=subprocess.run,
    sleeper=time.sleep,
    now=time.time,
    timeout_seconds=10,
):
    for image_name in image_names:
        if not process_running(image_name):
            continue
        result = runner(
            ["taskkill", "/F", "/T", "/IM", image_name],
            capture_output=True,
            text=True,
            timeout=20,
            **build_hidden_run_kwargs(),
        )
        output_text = " ".join(filter(None, [result.stdout, result.stderr])).strip()
        if process_running(image_name):
            raise RuntimeError(output_text or f"taskkill exited with code {result.returncode}")

    deadline = now() + timeout_seconds
    while now() < deadline:
        if not any(process_running(image_name) for image_name in image_names):
            return
        sleeper(0.5)

    remaining_processes = [
        image_name
        for image_name in image_names
        if process_running(image_name)
    ]
    if remaining_processes:
        raise RuntimeError(f"Steam processes still running: {', '.join(remaining_processes)}")


def launch_steam_client_executable(steam_path, get_steam_path=None, popen=subprocess.Popen, startfile=None):
    if not steam_path and get_steam_path:
        steam_path = get_steam_path()
    if not steam_path:
        raise FileNotFoundError("Steam installation not found")

    steam_path = Path(steam_path)
    steam_exe = steam_path / "steam.exe"
    if not steam_exe.exists():
        raise FileNotFoundError(f"Steam executable not found at {steam_exe}")

    try:
        popen([str(steam_exe)], cwd=str(steam_path))
    except Exception:
        open_uri(steam_exe, startfile=startfile)
    return steam_path


def build_hidden_worker_kwargs(platform=sys.platform, subprocess_module=subprocess):
    return build_hidden_process_kwargs(
        platform=platform,
        subprocess_module=subprocess_module,
    )


def start_steam_switch_worker_process(
    plugin_dir,
    steam_path,
    steamid64,
    python_executable=sys.executable,
    popen=subprocess.Popen,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    plugin_dir = Path(plugin_dir)
    worker_script = plugin_dir / "steam_switch_worker.py"
    if not worker_script.exists():
        raise FileNotFoundError(f"Steam switch worker not found at {worker_script}")

    return start_hidden_process(
        [python_executable, str(worker_script), str(steam_path), str(steamid64)],
        popen=popen,
        platform=platform,
        subprocess_module=subprocess_module,
        cwd=str(plugin_dir),
    )
