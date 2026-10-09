#!/usr/bin/env python3
"""Project K Forth REPL"""

import os
import re
import sys
from collections import deque

# Ensure projectk can be imported regardless of current working directory
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
except ImportError:
    PromptSession = None
    ANSI_SEQUENCES = None
    KeyBindings = None
    Keys = None

from projectk import VM, ForthError
import ai_bridge
import ai_tools


class Constant:
    """A callable object used by the Forth constant defining word."""

    def __init__(self, value):
        self.value = value

    def __call__(self, vm):
        vm.push(self.value)

    def __repr__(self):
        return f"Constant({self.value!r})"


class Value:
    """A callable object used by the Forth value defining word."""

    def __init__(self, value):
        self.value = value

    def __call__(self, vm):
        vm.push(self.value)

    def __repr__(self):
        return f"Value({self.value!r})"


BASE_F_PATH = os.path.join(SCRIPT_DIR, "base.f")
AI_F_PATH = os.path.join(SCRIPT_DIR, "ai.f")
AUXILIARY_F_PATH = os.path.join(SCRIPT_DIR, "auxiliary.f")


def _comment_line(vm: VM) -> None:
    vm.input._ensure_split()
    curr = vm.input.tib[vm.input.itib] if vm.input.itib < len(vm.input.tib) else ""
    pos = curr.find("\n")
    if pos < 0:
        vm.input.consume(len(curr))
    else:
        vm.input.consume(pos + 1)


def _comment_paren(vm: VM) -> None:
    vm.input.read(until=")")


def create_vm(base_file: str | None = None) -> VM:
    vm = VM(host={"Constant": Constant, "Value": Value, "ForthError": ForthError})
    vm.host.update({
        "vm": vm,
        "push": vm.push,
        "pop": vm.pop,
        "tos": vm.peek,
        "stack": vm.stack,
        "comma": vm.comma,
    })
    # Comments support
    vm.define("\\", _comment_line, immediate=True)
    vm.define("(", _comment_paren, immediate=True)

    target_base = base_file or BASE_F_PATH
    if os.path.isfile(target_base):
        with open(target_base, "r", encoding="utf-8") as f:
            bootstrap = f.read()
        vm.dictate(bootstrap)
    else:
        raise ForthError(f"Bootstrap file not found: {target_base}")
    ai_tools.install(vm)
    with open(AUXILIARY_F_PATH, "r", encoding="utf-8") as f:
        vm.dictate(f.read())
    if os.path.isfile(AI_F_PATH):
        with open(AI_F_PATH, "r", encoding="utf-8") as f:
            vm.dictate(f.read())
    return vm


def _process_one_line(vm: VM, line: str, state: dict) -> None:
    """Process one submitted editor buffer, which may contain multiple lines."""

    line = line.rstrip("\r\n")

    # Continue a host code block submitted over multiple editor buffers.
    if state["in_code_block"]:
        state["code_buffer"].append(line)
        block = "\n".join(state["code_buffer"])
        start_pos, _ = vm._find_code_terminator(block)
        if start_pos is not None:
            state["in_code_block"] = False
            state["code_buffer"] = []
            task = vm.dictate(block)
            if task.status == "paused":
                print("Task: paused")
            else:
                print(" ok")
        return

    # Check if this line starts a host code definition
    if re.match(r"^\s*code\b", line):
        start_pos, _ = vm._find_code_terminator(line)
        if start_pos is None:
            state["in_code_block"] = True
            state["code_buffer"] = [line]
            return

    # Blank line in normal mode
    if not line.strip() and not vm.compiling:
        return

    task = vm.dictate(line)
    if task.status == "paused":
        if vm.host.get("ai_pending_approval") or vm.host.get("ai_cleanup_pending"):
            state["ai_task"] = task
        else:
            print("Task: paused")
    elif not vm.compiling:
        print(" ok")


def _farewell(vm: VM) -> None:
    print("\nbye")
    try:
        ai_bridge.refresh_session_index(vm)
    except Exception as err:
        print(f"Could not refresh the local AI session list: {err}")

    session_id = ai_bridge._saved_session(vm)
    if session_id:
        title = ai_bridge._session_title(session_id) or "(untitled)"
        short_id = ai_bridge._short_id(session_id)
        print(f"Current AI session: {title} [{short_id}]")
        print(f'To resume it in a future Forth run, enter: s" {session_id}" ai-use')
    else:
        print("No AI session is selected in this Forth run.")


def _make_multiline_key_bindings(bindings_type=None):
    bindings_type = bindings_type or KeyBindings
    bindings = bindings_type()

    @bindings.add("c-m")
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @bindings.add("escape", "c-m")
    def _newline_with_escape_enter(event):
        event.current_buffer.insert_text("\n")

    @bindings.add("c-j")
    def _newline_with_control_j(event):
        event.current_buffer.insert_text("\n")

    return bindings


def _map_extended_enter_sequences(sequence_map, newline_key):
    if sequence_map is None or newline_key is None:
        return
    for sequence in ("\x1b[27;2;13~", "\x1b[13;2u"):
        sequence_map[sequence] = newline_key


def repl(vm: VM | None = None) -> None:
    if vm is None:
        vm = create_vm()

    if PromptSession is None:
        requirements = os.path.join(SCRIPT_DIR, "requirements.txt")
        print("Interactive REPL requires prompt_toolkit. Install it with: "
              f'{sys.executable} -m pip install -r "{requirements}"', file=sys.stderr)
        return

    # Modified Enter is reported distinctly only by terminals with extended
    # key support. Map the common xterm and Kitty encodings to the newline key.
    _map_extended_enter_sequences(ANSI_SEQUENCES, Keys.ControlJ if Keys is not None else None)

    prompt_session = PromptSession(
        multiline=True,
        key_bindings=_make_multiline_key_bindings(),
        prompt_continuation=lambda width, line_number, is_soft_wrap: "... ",
    )
    confirmation_session = PromptSession(multiline=False)

    print("Project K Forth REPL")
    print("Enter submits; Ctrl+J or Esc then Enter adds a line. Shift+Enter depends on terminal support.")
    print("Type 'words' to list words, 'ai:' to ask AI, or 'bye'/Ctrl-D to exit.\n")

    state = {"in_code_block": False, "code_buffer": [], "ai_task": None,
             "queued": deque(), "displayed_approval": None}

    while True:
        try:
            pending = vm.host.get("ai_pending_approval")
            cleanup = vm.host.get("ai_cleanup_pending")
            if pending:
                call_id = pending["action"].get("call_id")
                if state["displayed_approval"] != call_id:
                    print("\nAI proposes this Forth program:")
                    print(f"Purpose: {pending['purpose']}\n---\n{pending['source']}\n---")
                    state["displayed_approval"] = call_id
                print("Trust: run this and automatically approve future AI programs for this Forth run.")
                print("Yes: run this program once.")
                print("No: decline this program.")
                print("Cancel: cancel this AI mission.")
                prompt = "Run it? Type trust, yes, no, or cancel: "
            elif cleanup:
                prompt = (f"Delete session {cleanup['index']} ({ai_bridge._short_id(cleanup['session_id'])})? "
                          "Type delete or cancel: ")
            elif state["queued"]:
                raw_input = state["queued"].popleft()
                _process_one_line(vm, raw_input, state)
                continue
            else:
                prompt = ("... " if state["in_code_block"] or vm.compiling else
                          "> ")
            active_prompt = confirmation_session if pending or cleanup else prompt_session
            raw_input = active_prompt.prompt(prompt)

            clean_input = raw_input.replace("\r\n", "\n").replace("\r", "\n")

            pending = vm.host.get("ai_pending_approval")
            cleanup = vm.host.get("ai_cleanup_pending")
            if cleanup and not pending:
                choice = clean_input.strip().casefold()
                if choice == "delete":
                    vm.host["ai_cleanup_result"] = True
                elif choice == "cancel":
                    vm.host["ai_cleanup_result"] = False
                else:
                    if clean_input.strip():
                        state["queued"].append(clean_input)
                    continue
                vm.host.pop("ai_cleanup_pending", None)
                task = state.get("ai_task")
                state["ai_task"] = None
                if task:
                    task.resume()
                    if task.status == "paused" and (vm.host.get("ai_pending_approval") or vm.host.get("ai_cleanup_pending")):
                        state["ai_task"] = task
                    elif task.status == "done":
                        print(" ok")
                vm.host.pop("ai_cleanup_result", None)
                continue
            if pending:
                choice = clean_input.strip().casefold()
                if choice in {"trust", "yes", "y"}:
                    vm.host["ai_approval_result"] = "trust" if choice == "trust" else True
                elif choice in {"no", "n"}:
                    vm.host["ai_approval_result"] = False
                elif choice in {"cancel", "ai-cancel"}:
                    task = state.get("ai_task")
                    try:
                        ai_bridge.cancel_turn(vm)
                    except Exception as err:
                        print(f"Could not cancel remote turn: {err}")
                    if task:
                        task.cancel()
                    state["ai_task"] = None
                    vm.host.pop("ai_pending_approval", None)
                    vm.host.pop("ai_approval_result", None)
                    state["displayed_approval"] = None
                    print("AI task cancelled locally.")
                    continue
                else:
                    if clean_input.strip():
                        state["queued"].append(clean_input)
                    continue
                vm.host.pop("ai_pending_approval", None)
                state["displayed_approval"] = None
                task = state.get("ai_task")
                state["ai_task"] = None
                if task:
                    task.resume()
                    if task.status == "paused" and vm.host.get("ai_pending_approval"):
                        state["ai_task"] = task
                    elif task.status == "done":
                        print(" ok")
                continue
            if state["queued"]:
                state["queued"].append(clean_input)
            else:
                _process_one_line(vm, clean_input, state)

        except ForthError as err:
            print(f"Error: {err}")
            state["in_code_block"] = False
            state["code_buffer"] = []
            if vm.compiling:
                vm._discard_definition()
        except KeyboardInterrupt:
            print("\n<interrupted>")
            if vm.host.get("ai_pending_approval"):
                try:
                    ai_bridge.cancel_turn(vm)
                except Exception as err:
                    print(f"Could not cancel remote turn: {err}")
            if vm.host.get("ai_pending_approval") or vm.host.get("ai_cleanup_pending"):
                task = state.get("ai_task")
                if task:
                    task.cancel()
                state["ai_task"] = None
                vm.host.pop("ai_pending_approval", None)
                vm.host.pop("ai_approval_result", None)
                vm.host.pop("ai_cleanup_pending", None)
                vm.host.pop("ai_cleanup_result", None)
                state["displayed_approval"] = None
            state["in_code_block"] = False
            state["code_buffer"] = []
            if vm.compiling:
                vm._discard_definition()
        except (EOFError, SystemExit):
            _farewell(vm)
            break


def main() -> None:
    vm = create_vm()
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "-e" and len(sys.argv) > 2:
            expr = sys.argv[2]
            try:
                vm.dictate(expr)
            except ForthError as err:
                print(f"Error: {err}", file=sys.stderr)
                sys.exit(1)
        elif os.path.isfile(arg):
            with open(arg, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                vm.dictate(content)
            except ForthError as err:
                print(f"Error: {err}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Unknown argument or file not found: {arg}", file=sys.stderr)
            sys.exit(1)
    else:
        repl(vm)


if __name__ == "__main__":
    main()
