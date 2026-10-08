"""Standard-library bridge to the OpenAI Agents API."""
from __future__ import annotations

import base64
import io
import json
import os
import re
from contextlib import redirect_stderr, redirect_stdout
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SESSION_FILE = ROOT / ".ai_session.json"
API = "https://api.openai.com/v1/agents"


def load_dotenv():
    try:
        lines = (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _request(method, path, payload=None, stream=False):
    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY in py/.env or the process environment to use AI.")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
        "OpenAI-Beta": "agents=v1",
        "Accept": "text/event-stream" if stream else "application/json"})
    try:
        return urllib.request.urlopen(request, timeout=300)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace")
        raise RuntimeError(f"Agents API HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Agents API connection failed: {exc.reason}") from None


def _saved_session():
    try:
        value = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return value.get("session_id", "") if isinstance(value, dict) else ""
    except (OSError, ValueError):
        return ""


def _save_session(session_id):
    temporary = SESSION_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"session_id": session_id}, indent=2), encoding="utf-8")
    os.replace(temporary, SESSION_FILE)


def _create_session():
    skills_root = Path(os.environ.get("PROJECTK_AI_SKILLS_DIR", str(ROOT / "skills"))).expanduser()
    if not skills_root.is_absolute():
        skills_root = (ROOT / skills_root).resolve()
    skill = skills_root / "projectk-forth"
    if not (skill / "SKILL.md").is_file():
        raise RuntimeError(f"Project K Forth skill not found: {skill / 'SKILL.md'}")
    plugin = ROOT / "plugins" / "projectk-forth"
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, "projectk-forth/.codex-plugin/plugin.json")
        for path in sorted(skill.rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"Skill plugin cannot package symlink: {path}")
            if path.is_file():
                archive.write(path, "projectk-forth/skills/projectk-forth/" + path.relative_to(skill).as_posix())
    zipped = bundle.getvalue()
    if len(zipped) > 2 * 1024 * 1024:
        raise RuntimeError("Skill plugin ZIP exceeds 2 MiB.")
    tools = [
        {"type": "function", "name": "projectk_search_words",
         "description": "Search the current Forth dictionary and documentation.",
         "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"], "additionalProperties": False}},
        {"type": "function", "name": "projectk_run_forth",
         "description": "Propose Forth source for execution in the user's current local VM. The CLI asks for approval first.",
         "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "purpose": {"type": "string"}},
                        "required": ["source", "purpose"], "additionalProperties": False}},
    ]
    payload = {
        "agent": {"model": os.environ.get("PROJECTK_AI_MODEL", "gpt-6-astra"), "tools": tools,
                  "instructions": "You assist with Project K Forth. Follow the Project K Forth skill. "
                  "Use the live dictionary tool before relying on unfamiliar words. Only the local Forth "
                  "tool can execute code, and it always requires explicit user approval."},
        "environment": {"type": "openai_hosted", "plugins": [{"type": "inline",
            "name": manifest["name"], "description": manifest["description"],
            "source": {"type": "base64", "media_type": "application/zip",
                       "data": base64.b64encode(zipped).decode("ascii")}}]},
    }
    with _request("POST", "/sessions", payload) as response:
        result = json.load(response)
    if not result.get("id"):
        raise RuntimeError("Agents API response did not include a session ID.")
    _save_session(result["id"])
    return result["id"]


def _stream(session_id, event):
    response = _request("GET", f"/sessions/{session_id}/events?stream=true", stream=True)
    try:
        # Subscribe before creating the turn so the first event cannot be missed.
        with _request("POST", f"/sessions/{session_id}/events", {"events": [event]}) as accepted:
            accepted.read()
        data = []
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line and data:
                joined = "\n".join(data)
                data.clear()
                if joined != "[DONE]":
                    try:
                        yield json.loads(joined)
                    except json.JSONDecodeError:
                        pass
        if data and "\n".join(data) != "[DONE]":
            yield json.loads("\n".join(data))
    finally:
        response.close()


def _tool_result(session_id, action, success, output="", error=""):
    event = {"type": "agent.session.input.tool_result", "turn_id": action["turn_id"],
             "call_id": action["call_id"], "success": success}
    event["output" if success else "error"] = output if success else error
    with _request("POST", f"/sessions/{session_id}/events", {"events": [event]}) as response:
        response.read()


def _current_actions(session_id):
    """Fetch current pending calls; event payloads are only notifications."""
    with _request("GET", f"/sessions/{session_id}") as response:
        session = json.load(response)
    return session.get("status"), session.get("required_actions") or []


def cancel_turn():
    session_id = _saved_session()
    if session_id:
        with _request("POST", f"/sessions/{session_id}/events", {
                "events": [{"type": "agent.session.input.cancel"}]}) as response:
            response.read()


def _search(vm, query):
    terms = query.casefold().split()
    matches = []
    for name, word in vm.words.items():
        help_text = str(getattr(word, "help", "") or "")
        comment = str(getattr(word, "comment", "") or "")
        source = str(getattr(word, "source", "") or "")
        if all(term in f"{name} {help_text} {comment} {source}".casefold() for term in terms):
            matches.append({"name": name, "help": help_text, "comment": comment,
                            "source": source[:1200], "immediate": bool(word.immediate)})
        if len(matches) >= 30:
            break
    return json.dumps(matches, ensure_ascii=False)


def _run(vm, source):
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            task = vm.dictate(source)
        if task.status == "paused":
            task.cancel()
            return "{\"status\":\"error\",\"error\":\"Async pause is not supported in AI execution\"}"
        result = {"status": task.status, "stack": repr(vm.stack),
                  "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
    except Exception as exc:
        result = {"status": "error", "error": str(exc), "stack": repr(vm.stack),
                  "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
    return json.dumps(result, ensure_ascii=False)


def ask(vm, prompt):
    """Yield text and approval events; resumes after REPL writes ai_approval_result."""
    if not prompt.strip():
        raise RuntimeError("ai: needs a prompt on the same line.")
    session_id = _saved_session() or _create_session()
    message = {"type": "agent.session.input.message", "input": [{"role": "user", "content": [
        {"type": "input_text", "text": prompt}]}]}
    for event in _stream(session_id, message):
        kind = event.get("type", "")
        if kind == "agent.session.turn.output_text.delta":
            yield {"kind": "text", "text": event.get("delta", "")}
        elif kind == "agent.session.turn.output_text.done":
            yield {"kind": "text_done", "text": event.get("text", "")}
        elif kind == "agent.session.requires_action":
            session_status, actions = _current_actions(session_id)
            if session_status != "requires_action":
                raise RuntimeError(
                    f"Agents API signaled required action but session status is {session_status!r}."
                )
            for action in actions:
                name = action.get("name")
                arguments = action.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if name == "projectk_search_words":
                    _tool_result(session_id, action, True, _search(vm, str(arguments.get("query", ""))))
                elif name == "projectk_run_forth":
                    yield {"kind": "approval", "action": action,
                           "source": str(arguments.get("source", "")),
                           "purpose": str(arguments.get("purpose", ""))}
                    approved = bool(vm.host.pop("ai_approval_result", False))
                    if approved:
                        status, still_pending = _current_actions(session_id)
                        if status != "requires_action" or not any(
                                pending.get("call_id") == action.get("call_id")
                                for pending in still_pending):
                            raise RuntimeError(
                                "This approval request expired before execution. "
                                "The Forth program was not run; please ask AI to propose it again."
                            )
                        execution = _run(vm, str(arguments.get("source", "")))
                        try:
                            _tool_result(session_id, action, True, execution)
                        except Exception as exc:
                            raise RuntimeError(
                                "The approved Forth program has already run locally, but the Agents API "
                                f"did not accept its result: {exc}. Check the local VM/output before retrying. "
                                f"Execution result: {execution}"
                            ) from None
                    else:
                        _tool_result(session_id, action, False, error="User declined execution.")
                else:
                    _tool_result(session_id, action, False, error=f"Unknown function: {name}")
        elif kind in ("error", "agent.session.failed", "agent.session.environment.failed", "agent.session.turn.failed"):
            detail = event.get("error") or event.get("turn", {}).get("error") or event
            raise RuntimeError(f"Agents API {kind}: {detail}")
        elif kind == "agent.session.turn.completed":
            return


def install(vm):
    def run_prompt(current_vm, prompt, push_response=False):
        answer = []
        for event in ask(current_vm, prompt):
            if event["kind"] == "text":
                if push_response:
                    answer.append(event["text"])
                else:
                    print(event["text"], end="", flush=True)
            elif event["kind"] == "text_done":
                if push_response:
                    answer[:] = [event["text"]]
                else:
                    print()
            elif event["kind"] == "approval":
                current_vm.host["ai_pending_approval"] = event
                yield current_vm.pause()
        if push_response:
            current_vm.push("".join(answer))

    def ai_line(current_vm):
        current_vm.input._ensure_split()
        current = current_vm.input.tib[current_vm.input.itib] if current_vm.input.itib < len(current_vm.input.tib) else ""
        prompt = current_vm.input.rest().strip() if "\n" not in current else current_vm.input.read(until="\n").strip()
        try:
            yield from run_prompt(current_vm, prompt)
        except KeyboardInterrupt:
            try:
                cancel_turn()
            except Exception:
                pass
            raise

    def ai_stack(current_vm):
        prompt = current_vm.pop()
        if not isinstance(prompt, str):
            raise RuntimeError("(ai) expects a string on the data stack.")
        try:
            yield from run_prompt(current_vm, prompt, push_response=True)
        except KeyboardInterrupt:
            try:
                cancel_turn()
            except Exception:
                pass
            raise

    def new_session(current_vm):
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Could not clear local session: {exc}") from None
        print("Local AI session cleared; the next request creates a new session.")

    def status(current_vm):
        print("AI session: " + (_saved_session() or "not created"))

    def cancel_word(current_vm):
        if current_vm.host.get("ai_pending_approval"):
            cancel_turn()
            print("Sent an Agents API cancel request.")
        else:
            print("No AI task is waiting for local approval; use cancel at its confirmation prompt.")

    vm.define("(ai-line)", ai_line, help="Host implementation used by ai.f.")
    vm.define("(ai)", ai_stack, help="( prompt-string -- response-string ) Ask AI.")
    vm.define("ai-new", new_session, help="Clear the saved session ID.")
    vm.define("ai-status", status, help="Show the saved session ID, if any.")
    vm.define("ai-cancel", cancel_word, help="Cancel the active Agents API turn.")
