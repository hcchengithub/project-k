"""Standard-library bridge to the OpenAI Agents API."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
import re
from contextlib import redirect_stderr, redirect_stdout
import urllib.error
import urllib.parse
import urllib.request
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
    return _session_store().get("active_session_id") or ""


def _session_store():
    try:
        value = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {"active_session_id": "", "sessions": []}
        if isinstance(value.get("sessions"), list):
            return {"active_session_id": value.get("active_session_id") or "",
                    "sessions": value["sessions"]}
        # Migrate the original one-session file without losing its saved ID.
        session_id = value.get("session_id", "")
        return {"active_session_id": session_id,
                "sessions": ([{"id": session_id}] if session_id else [])}
    except (OSError, ValueError):
        return {"active_session_id": "", "sessions": []}


def _write_session_store(store):
    temporary = SESSION_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, SESSION_FILE)


def _save_session(session_id, metadata=None):
    store = _session_store()
    entries = store["sessions"]
    record = next((item for item in entries if item.get("id") == session_id), None)
    if record is None:
        record = {"id": session_id}
        entries.insert(0, record)
    if metadata:
        record.update({key: value for key, value in metadata.items() if value is not None})
    store["active_session_id"] = session_id
    _write_session_store(store)


def _remember_remote_sessions(sessions):
    store = _session_store()
    by_id = {item.get("id"): item for item in store["sessions"] if item.get("id")}
    merged = []
    for session in sessions:
        session_id = session.get("id")
        if not session_id:
            continue
        record = by_id.get(session_id, {"id": session_id})
        record.update({key: session.get(key) for key in ("created_at", "last_active_at")
                       if session.get(key) is not None})
        merged.append(record)
    merged_ids = {item.get("id") for item in merged}
    for record in store["sessions"]:
        if record.get("id") not in merged_ids:
            merged.append(record)
    store["sessions"] = merged
    _write_session_store(store)


def _forget_session(session_id):
    store = _session_store()
    store["sessions"] = [item for item in store["sessions"] if item.get("id") != session_id]
    if store.get("active_session_id") == session_id:
        store["active_session_id"] = ""
    _write_session_store(store)


def _api_get(path):
    with _request("GET", path) as response:
        return json.load(response)


def _list_remote_sessions():
    sessions = []
    after = ""
    while True:
        query = urllib.parse.urlencode({"limit": 100, "order": "desc", **({"after": after} if after else {})})
        page = _api_get(f"/sessions?{query}")
        sessions.extend(page.get("data") or [])
        if not page.get("has_more") or not page.get("last_id") or page["last_id"] == after:
            return sessions
        after = page["last_id"]


def _list_session_items(session_id):
    items = []
    after = ""
    while True:
        query = urllib.parse.urlencode({"limit": 100, "order": "asc", **({"after": after} if after else {})})
        page = _api_get(f"/sessions/{urllib.parse.quote(session_id, safe='')}/items?{query}")
        items.extend(page.get("data") or [])
        if not page.get("has_more") or not page.get("last_id") or page["last_id"] == after:
            return items
        after = page["last_id"]


def _session_snapshot(vm, key="ai_session_rows"):
    rows = vm.host.get(key)
    if rows is None:
        raise RuntimeError("Run ai-sessions first to refresh the remote list and its sequence numbers.")
    return rows


def _selected_row(vm, index, key="ai_session_rows"):
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        raise RuntimeError("Session number must be a positive integer.")
    rows = _session_snapshot(vm, key)
    if index > len(rows):
        raise RuntimeError(f"No item {index}; the current list has {len(rows)} entries.")
    return rows[index - 1]


def _format_time(value):
    if not value:
        return "unknown"
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError, TypeError, OSError, OverflowError):
        return str(value)


def _delete_session(session_id):
    with _request("DELETE", f"/sessions/{urllib.parse.quote(session_id, safe='')}") as response:
        return json.load(response)


def _create_session(prompt):
    skills_root = Path(os.environ.get("PROJECTK_AI_SKILLS_DIR", str(ROOT / "skills"))).expanduser()
    if not skills_root.is_absolute():
        skills_root = (ROOT / skills_root).resolve()
    skill = skills_root / "projectk-forth"
    if not (skill / "SKILL.md").is_file():
        raise RuntimeError(f"Project K Forth skill not found: {skill / 'SKILL.md'}")
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    reference_path = skill / "references" / "forth-reference.md"
    reference_text = reference_path.read_text(encoding="utf-8") if reference_path.is_file() else ""
    # With environment=none there is no filesystem in which to load a plugin;
    # include the Project K guidance directly in the agent instructions.
    skill_text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", skill_text, count=1, flags=re.S)
    instructions = (
        "You assist with Project K Forth. Use the live dictionary tool before relying on unfamiliar words. "
        "Only the local Forth tool can execute code. The local CLI controls approval: each proposal requires user approval unless the user chooses Trust, which approves future proposals for this REPL process only. The user can restore per-proposal approval with ai-confirm. Never infer Trust from a prior Yes.\n\n"
        + skill_text + ("\n\nForth reference:\n" + reference_text if reference_text else "")
    )
    if len(instructions.encode("utf-8")) > 100_000:
        raise RuntimeError("Project K Forth skill text is too large to include in agent instructions.")
    tools = [
        {"type": "function", "name": "projectk_search_words",
         "description": "Search the current Forth dictionary and documentation.",
         "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"], "additionalProperties": False}},
        {"type": "function", "name": "projectk_run_forth",
         "description": "Propose Forth source for execution in the user's current local VM. The CLI applies its current approval mode.",
         "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "purpose": {"type": "string"}},
                        "required": ["source", "purpose"], "additionalProperties": False}},
    ]
    payload = {
        "agent": {"model": os.environ.get("PROJECTK_AI_MODEL", "gpt-6-astra"), "tools": tools,
                  "instructions": instructions},
        "environment": {"type": "none"},
        "input": prompt,
        "stream": True,
    }
    return _event_stream(_request("POST", "/sessions", payload, stream=True))


def _event_stream(response):
    try:
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


def _stream(session_id, event):
    encoded_id = urllib.parse.quote(session_id, safe="")
    response = _request("GET", f"/sessions/{encoded_id}/events?stream=true", stream=True)
    try:
        # Subscribe before creating the turn so the first event cannot be missed.
        with _request("POST", f"/sessions/{encoded_id}/events", {"events": [event]}) as accepted:
            accepted.read()
        yield from _event_stream(response)
    finally:
        if not response.closed:
            response.close()


def _tool_result(session_id, action, success, output="", error=""):
    event = {"type": "agent.session.input.tool_result", "turn_id": action["turn_id"],
             "call_id": action["call_id"], "success": success}
    event["output" if success else "error"] = output if success else error
    encoded_id = urllib.parse.quote(session_id, safe="")
    with _request("POST", f"/sessions/{encoded_id}/events", {"events": [event]}) as response:
        response.read()


def _current_actions(session_id):
    """Fetch current pending calls; event payloads are only notifications."""
    session = _api_get(f"/sessions/{urllib.parse.quote(session_id, safe='')}")
    return session.get("status"), session.get("required_actions") or []


def cancel_turn():
    session_id = _saved_session()
    if session_id:
        with _request("POST", f"/sessions/{urllib.parse.quote(session_id, safe='')}/events", {
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


def _session_id_from_event(event):
    session = event.get("session") or event.get("data") or {}
    if isinstance(session, dict):
        return session.get("id") or session.get("session_id") or event.get("session_id")
    return event.get("session_id")


def ask(vm, prompt):
    """Yield text and approval events; resumes after REPL writes ai_approval_result."""
    if not prompt.strip():
        raise RuntimeError("ai: needs a prompt on the same line.")
    session_id = _saved_session()
    message = {"type": "agent.session.input.message", "input": [{"role": "user", "content": [
        {"type": "input_text", "text": prompt}]}]}
    events = _stream(session_id, message) if session_id else _create_session(prompt)
    for event in events:
        if not session_id:
            session_id = _session_id_from_event(event)
            if session_id:
                created = event.get("session") or event.get("data") or {}
                _save_session(session_id, {key: created.get(key)
                                           for key in ("created_at", "last_active_at")})
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
                    proposal = {"kind": "approval", "action": action,
                                "source": str(arguments.get("source", "")),
                                "purpose": str(arguments.get("purpose", ""))}
                    if vm.host.get("ai_trusted", False):
                        yield {**proposal, "trusted": True}
                        approved = True
                    else:
                        yield proposal
                        approval = vm.host.pop("ai_approval_result", False)
                        if isinstance(approval, str) and approval.casefold() == "trust":
                            vm.host["ai_trusted"] = True
                            approved = True
                        else:
                            approved = bool(approval)
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
    if not session_id:
        raise RuntimeError("Agents API stream ended without returning the new session ID.")


def install(vm):
    def run_prompt(current_vm, prompt, push_response=False):
        answer = []
        ai_started = False
        ai_line_start = True
        for event in ask(current_vm, prompt):
            if event["kind"] == "text":
                if push_response:
                    answer.append(event["text"])
                else:
                    text = event["text"]
                    if text and not ai_started:
                        print()
                        ai_started = True
                    for part in text.splitlines(keepends=True):
                        if ai_line_start:
                            print("🤖 ", end="")
                        print(part, end="", flush=True)
                        ai_line_start = part.endswith("\n") or part.endswith("\r")
            elif event["kind"] == "text_done":
                if push_response:
                    answer[:] = [event["text"]]
                else:
                    if ai_started and not ai_line_start:
                        print()
                    ai_started = False
                    ai_line_start = True
            elif event["kind"] == "approval":
                if event.get("trusted"):
                    print("\n🤖 AI proposes this Forth program (auto-approved for this Forth run):")
                    print(f"Purpose: {event['purpose']}\n---\n{event['source']}\n---")
                    continue
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
        store = _session_store()
        store["active_session_id"] = ""
        _write_session_store(store)
        print("A fresh conversation will be created on your next ai: request; session history is kept.")

    def sessions(current_vm):
        rows = _list_remote_sessions()
        _remember_remote_sessions(rows)
        current_vm.host["ai_session_rows"] = rows
        if not rows:
            print("No remote sessions found.")
            return
        active_id = _saved_session()
        print(f"Remote sessions: {len(rows)} (newest first)")
        for index, row in enumerate(rows, 1):
            env = row.get("environment") or {}
            marker = " *" if row.get("id") == active_id else ""
            print(f"{index:>3}. {row.get('id')}  {_format_time(row.get('created_at'))}  "
                  f"{row.get('status', 'unknown')}  {(row.get('agent') or {}).get('model', 'unknown')}  "
                  f"env={env.get('type', 'unknown')}{marker}")

    def selected_session(current_vm):
        index = current_vm.pop()
        row = _selected_row(current_vm, index)
        return index, row

    def session_details(current_vm):
        index, row = selected_session(current_vm)
        detail = _api_get(f"/sessions/{urllib.parse.quote(row['id'], safe='')}")
        agent = detail.get("agent") or {}
        env = detail.get("environment") or {}
        usage = detail.get("usage") or {}
        print(f"Session {index}: {detail.get('id')}")
        print(f"Created: {_format_time(detail.get('created_at'))}")
        print(f"Last active: {_format_time(detail.get('last_active_at'))}")
        print(f"Status: {detail.get('status', 'unknown')}")
        print(f"Model: {agent.get('model', 'unknown')}")
        print(f"Environment: {env.get('type', 'unknown')} (id={env.get('id', 'none')}, "
              f"size={env.get('container_size', 'n/a')})")
        print(f"Usage: input={usage.get('input_tokens', 0)} output={usage.get('output_tokens', 0)} "
              f"total={usage.get('total_tokens', 0)} tokens")
        if detail.get("error"):
            print(f"Error: {detail['error']}")

    def use_session(current_vm):
        index, row = selected_session(current_vm)
        detail = _api_get(f"/sessions/{urllib.parse.quote(row['id'], safe='')}")
        _save_session(row["id"], {"created_at": detail.get("created_at")})
        print(f"Using session {index}: {row['id']}")

    def show_transcript(current_vm, include_items=False):
        index, row = selected_session(current_vm)
        items = _list_session_items(row["id"])
        if include_items:
            for item in items:
                print(json.dumps(item, ensure_ascii=False, indent=2))
            if not items:
                print("No saved items.")
            return
        shown = 0
        for item in items:
            if item.get("type") != "message" or item.get("role") not in {"user", "assistant"}:
                continue
            parts = []
            for part in item.get("content") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            text = "".join(parts).strip()
            if text:
                print(f"[{item['role']}]\n{text}\n")
                shown += 1
        if not shown:
            print(f"Session {index} has no user/assistant text items.")

    def containers(current_vm):
        session_rows = _session_snapshot(current_vm)
        rows = []
        for session in session_rows:
            detail = _api_get(f"/sessions/{urllib.parse.quote(session['id'], safe='')}")
            env = detail.get("environment") or {}
            if env.get("type") != "openai_hosted" or not env.get("id"):
                continue
            try:
                env_detail = _api_get(f"/environments/{urllib.parse.quote(env['id'], safe='')}")
                status = env_detail.get("status", "unknown")
            except RuntimeError as exc:
                env_detail = {}
                status = f"unavailable ({exc})"
            rows.append({"session_id": session["id"], "environment_id": env["id"],
                         "container_size": env.get("container_size"), "status": status,
                         "details": env_detail})
        current_vm.host["ai_container_rows"] = rows
        if not rows:
            print("No hosted environments are linked to the listed sessions.")
            return
        print(f"Hosted environments linked to sessions: {len(rows)}")
        for index, row in enumerate(rows, 1):
            print(f"{index:>3}. env={row['environment_id']}  status={row['status']}  "
                  f"size={row.get('container_size') or 'unknown'}  session={row['session_id']}")

    def container_details(current_vm):
        index = current_vm.pop()
        rows = _session_snapshot(current_vm, "ai_container_rows")
        if not isinstance(index, int) or isinstance(index, bool) or index < 1 or index > len(rows):
            raise RuntimeError(f"Container number must be between 1 and {len(rows)}.")
        row = rows[index - 1]
        print(f"Environment {index}: {row['environment_id']}")
        print(f"Session: {row['session_id']}")
        print(f"Status: {row['status']}")
        print(json.dumps(row.get("details") or {}, ensure_ascii=False, indent=2))

    def cleanup_session(current_vm):
        index, row = selected_session(current_vm)
        session_id = row["id"]
        print(f"This permanently deletes session {index}: {session_id} and its conversation.")
        print("If it has a hosted sandbox, deletion also requests sandbox cleanup.")
        print("Type 'delete' to confirm, or 'cancel' to keep the session.")
        current_vm.host["ai_cleanup_pending"] = {"index": index, "session_id": session_id}
        yield current_vm.pause()
        approved = bool(current_vm.host.pop("ai_cleanup_result", False))
        current_vm.host.pop("ai_cleanup_pending", None)
        if not approved:
            print("AI session kept.")
            return
        result = _delete_session(session_id)
        if result.get("deleted") is not True:
            raise RuntimeError("Agents API did not confirm session deletion.")
        _forget_session(session_id)
        current_vm.host.pop("ai_session_rows", None)
        current_vm.host.pop("ai_container_rows", None)
        print("AI session deleted from the API; physical cleanup may continue asynchronously.")

    def status(current_vm):
        store = _session_store()
        print("Active AI session: " + (_saved_session() or "none (next request starts a new session)"))
        print(f"Locally indexed sessions: {len(store['sessions'])}")

    def confirm_ai(current_vm):
        current_vm.host.pop("ai_trusted", None)
        print("AI Forth programs will require approval again.")

    def cancel_word(current_vm):
        if current_vm.host.get("ai_pending_approval"):
            cancel_turn()
            print("Sent an Agents API cancel request.")
        else:
            print("No AI task is waiting for local approval; use cancel at its confirmation prompt.")

    vm.define("(ai-line)", ai_line, help="Host implementation used by ai.f.")
    vm.define("(ai)", ai_stack, help="( prompt-string -- response-string ) Ask AI.")
    vm.define("ai-new", new_session, help="Start a fresh conversation on the next AI request; keep history.")
    vm.define("ai-sessions", sessions, help="List remote sessions; sequence numbers are newest first.")
    vm.define("ai-session", session_details, help="( session-number -- ) Show remote session details.")
    vm.define("ai-use", use_session, help="( session-number -- ) Select a remote session for follow-up chat.")
    vm.define("ai-transcript", lambda current_vm: show_transcript(current_vm),
              help="( session-number -- ) Show user and assistant text.")
    vm.define("ai-items", lambda current_vm: show_transcript(current_vm, True),
              help="( session-number -- ) Show all saved session items, including tool interactions.")
    vm.define("ai-containers", containers, help="List hosted environments linked to remote sessions.")
    vm.define("ai-container", container_details, help="( container-number -- ) Show hosted environment details.")
    vm.define("ai-cleanup", cleanup_session, help="( session-number -- ) Delete a remote session after confirmation.")
    vm.define("ai-status", status, help="Show the active session and local index count.")
    vm.define("ai-confirm", confirm_ai, help="Require approval for each AI Forth program again.")
    vm.define("ai-cancel", cancel_word, help="Cancel the active Agents API turn.")
