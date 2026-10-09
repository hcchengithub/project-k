"""AI-facing local system, shell, curl, and HTTP words for Project K."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


_OUTPUT_LIMIT = 64 * 1024
_PROCESS_TIMEOUT = 60
_HTTP_TIMEOUT = 30


def _clip(value):
    value = value or ""
    return value[:_OUTPUT_LIMIT], len(value) > _OUTPUT_LIMIT


def _decode_partial(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _run_process(argv, input_text=None, timeout=_PROCESS_TIMEOUT):
    try:
        completed = subprocess.run(
            argv,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout, out_truncated = _clip(_decode_partial(exc.stdout))
        stderr, err_truncated = _clip(_decode_partial(exc.stderr))
        return {
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": True,
            "truncated": out_truncated or err_truncated,
            "error": f"Process exceeded the {timeout}-second time limit.",
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "truncated": False,
            "error": str(exc),
        }

    stdout, out_truncated = _clip(completed.stdout)
    stderr, err_truncated = _clip(completed.stderr)
    return {
        "exit_code": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": False,
        "truncated": out_truncated or err_truncated,
    }


def _program_info(name, version_args):
    path = shutil.which(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    result = _run_process([path, *version_args], timeout=8)
    version_text = result.get("stdout", "").strip() or result.get("stderr", "").strip()
    version = next((line.strip() for line in version_text.splitlines() if line.strip()), None)
    return {"available": True, "path": path, "version": version}


def _windows_wsl_info():
    wsl_path = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl_path:
        return {"available": False, "path": None, "distro": None, "distros": []}

    listed = _run_process([wsl_path, "--list", "--quiet"], timeout=10)
    raw = (listed.get("stdout") or "").replace("\x00", "").replace("\ufeff", "")
    distros = [line.strip() for line in raw.splitlines() if line.strip()]
    configured = os.environ.get("PROJECTK_WSL_DISTRO", "Ubuntu")
    distro = next((item for item in distros if item.casefold() == configured.casefold()), None)
    if distro is None and configured.casefold() == "ubuntu":
        distro = next((item for item in distros if item.casefold().startswith("ubuntu")), None)
    info = {
        "available": bool(distro),
        "path": wsl_path,
        "distro": distro,
        "distros": distros,
    }
    if listed.get("exit_code") not in (0, None):
        info["error"] = listed.get("stderr") or "Could not list WSL distributions."
    return info


def _detect_system_info():
    is_windows = os.name == "nt"
    release = platform.release()
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME")) or "microsoft" in release.casefold()
    wsl_distro = os.environ.get("WSL_DISTRO_NAME") if is_wsl else None

    prefix = os.path.normcase(os.path.abspath(sys.prefix))
    base_prefix = os.path.normcase(os.path.abspath(sys.base_prefix))
    venv_active = prefix != base_prefix

    pwsh_name = "pwsh.exe" if is_windows else "pwsh"
    pwsh = _program_info(
        pwsh_name,
        ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    )

    if is_windows:
        wsl = _windows_wsl_info()
        if wsl.get("available"):
            bash_probe = _run_process([
                wsl["path"], "-d", wsl["distro"], "--exec", "bash", "--version"
            ], timeout=10)
            version_text = bash_probe.get("stdout", "").strip() or bash_probe.get("stderr", "").strip()
            bash = {
                "available": bash_probe.get("exit_code") == 0,
                "path": wsl["path"],
                "distro": wsl["distro"],
                "version": next((line.strip() for line in version_text.splitlines() if line.strip()), None),
            }
        else:
            bash = {"available": False, "path": None, "distro": None, "version": None}
    else:
        wsl = {"available": is_wsl, "path": None, "distro": wsl_distro, "distros": []}
        bash = _program_info("bash", ["--version"])

    curl_name = "curl.exe" if is_windows else "curl"
    curl = _program_info(curl_name, ["--version"])
    if is_windows and not curl["available"]:
        curl = _program_info("curl", ["--version"])

    return {
        "os": platform.system(),
        "platform": sys.platform,
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "venv": {
            "active": venv_active,
            "path": sys.prefix if venv_active else None,
        },
        "wsl": {
            "active": is_wsl,
            "available": wsl.get("available", False),
            "distro": wsl.get("distro") or wsl_distro,
            "path": wsl.get("path"),
            "distros": wsl.get("distros", []),
        },
        "shells": {
            "pwsh": pwsh,
            "bash": bash,
            "curl": curl,
        },
    }


def _system_info(vm):
    word = vm.words.get("system_info")
    if word is None:
        return _detect_system_info()
    cached = word.properties.get("system_info")
    if cached is None:
        cached = _detect_system_info()
        word.properties["system_info"] = cached
    return cached


def _error(message):
    return {
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "error": message,
    }


def _run_pwsh_script(vm, script):
    if not isinstance(script, str):
        return _error("run_pwsh expects a script string.")
    info = _system_info(vm)["shells"]["pwsh"]
    if not info.get("available"):
        return _error("PowerShell 7 (pwsh) is not available in this environment.")
    return _run_process([
        info["path"], "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"
    ], input_text=script)


def _run_bash_script(vm, script):
    if not isinstance(script, str):
        return _error("run_bash expects a script string.")
    info = _system_info(vm)
    if info["os"] == "Windows":
        wsl = info["wsl"]
        if not wsl.get("available") or not wsl.get("path") or not wsl.get("distro"):
            return _error("WSL with an Ubuntu distribution is not available.")
        argv = [
            wsl["path"], "-d", wsl["distro"], "--exec",
            "bash", "--noprofile", "--norc", "-s",
        ]
    else:
        bash = info["shells"]["bash"]
        if not bash.get("available") or not bash.get("path"):
            return _error("Bash is not available in this environment.")
        argv = [bash["path"], "--noprofile", "--norc", "-s"]
    return _run_process(argv, input_text=script)


def _run_curl(vm, arguments):
    if not isinstance(arguments, (list, tuple)) or not all(isinstance(item, str) for item in arguments):
        return _error("run_curl expects a list of curl argument strings, including the URL.")
    info = _system_info(vm)["shells"]["curl"]
    if not info.get("available") or not info.get("path"):
        return _error("curl is not available in this environment.")
    return _run_process([info["path"], *arguments])


def _http_body_text(raw, headers):
    charset = None
    try:
        charset = headers.get_content_charset()
    except AttributeError:
        pass
    try:
        return raw.decode(charset or "utf-8", "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _http_result(status, headers, body):
    raw = body.read(_OUTPUT_LIMIT + 1)
    truncated = len(raw) > _OUTPUT_LIMIT
    raw = raw[:_OUTPUT_LIMIT]
    return {
        "status_code": status,
        "headers": {str(key): str(value) for key, value in headers.items()},
        "body": _http_body_text(raw, headers),
        "truncated": truncated,
    }


def _run_http(request):
    if not isinstance(request, dict):
        return {"error": "run_http expects a request mapping with a url field."}
    url = request.get("url")
    if not isinstance(url, str):
        return {"error": "run_http request url must be a string."}
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        return {"error": str(exc)}
    if parsed.scheme.casefold() not in ("http", "https") or not parsed.netloc:
        return {"error": "run_http only supports absolute http:// or https:// URLs."}

    method = request.get("method", "GET")
    headers = request.get("headers", {})
    body = request.get("body")
    if not isinstance(method, str) or not method:
        return {"error": "run_http method must be a nonempty string."}
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
    ):
        return {"error": "run_http headers must be a mapping of strings to strings."}
    if body is not None and not isinstance(body, str):
        return {"error": "run_http body must be a string when provided."}

    data = body.encode("utf-8") if body is not None else None
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method.upper(),
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as response:
            return _http_result(response.status, response.headers, response)
    except urllib.error.HTTPError as exc:
        try:
            return _http_result(exc.code, exc.headers, exc)
        finally:
            exc.close()
    except Exception as exc:
        return {"error": str(exc)}


def install(vm):
    def system_info(current_vm):
        current_vm.push(_system_info(current_vm))

    def run_pwsh(current_vm):
        current_vm.push(_run_pwsh_script(current_vm, current_vm.pop()))

    def run_bash(current_vm):
        current_vm.push(_run_bash_script(current_vm, current_vm.pop()))

    def run_curl(current_vm):
        current_vm.push(_run_curl(current_vm, current_vm.pop()))

    def run_http(current_vm):
        current_vm.push(_run_http(current_vm.pop()))

    vm.define(
        "system_info",
        system_info,
        help="( -- info ) Return cached host, Python venv, WSL, and shell details.",
        comment="The first call detects the host and caches stable details on this word object's properties for this VM lifetime.",
    )
    vm.define(
        "run_pwsh",
        run_pwsh,
        help="( script-string -- result ) Run a PowerShell 7 script without profiles.",
        comment="Pass a script string. Returns a mapping with exit_code, stdout, stderr, timed_out, truncated, and optional error details. The script runs locally with the current user's permissions.",
    )
    vm.define(
        "run_bash",
        run_bash,
        help="( script-string -- result ) Run a Bash script in the current Linux environment or configured Ubuntu WSL distro.",
        comment="Pass a script string. Returns a mapping with exit_code, stdout, stderr, timed_out, truncated, and optional error details. Windows hosts use the configured Ubuntu WSL distro; Linux hosts use native Bash.",
    )
    vm.define(
        "run_curl",
        run_curl,
        help="( argument-list -- result ) Run curl with a list of argument strings; include the URL.",
        comment="Pass a Python list of strings, for example with py>> on its own line. Arguments are passed directly to curl.exe or curl without shell parsing.",
    )
    vm.define(
        "run_http",
        run_http,
        help="( request-mapping -- response ) Send one HTTP request using Python's standard library.",
        comment="Request mapping fields: url (required), method (default GET), headers (string mapping), and body (optional string). Supports HTTP and HTTPS; returns status_code, headers, body, or an error mapping.",
    )
