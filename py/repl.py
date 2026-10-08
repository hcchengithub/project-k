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
    import readline
except ImportError:
    pass

from projectk import VM, ForthError
import ai_bridge


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
    ai_bridge.install(vm)
    if os.path.isfile(AI_F_PATH):
        with open(AI_F_PATH, "r", encoding="utf-8") as f:
            vm.dictate(f.read())
    return vm


def _process_one_line(vm: VM, line: str, state: dict) -> None:
    line = line.rstrip("\r\n")

    # In multi-line code block mode (`code ... end-code`)
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
        if vm.host.get("ai_pending_approval"):
            state["ai_task"] = task
        else:
            print("Task: paused")
    elif not vm.compiling:
        print(" ok")


def repl(vm: VM | None = None) -> None:
    if vm is None:
        vm = create_vm()

    print("Project K Forth REPL")
    print("Type 'words' to list words, 'ai: <prompt>' to ask AI, or 'bye'/Ctrl-D to exit.\n")

    state = {"in_code_block": False, "code_buffer": [], "ai_task": None,
             "queued": deque(), "displayed_approval": None}

    while True:
        try:
            pending = vm.host.get("ai_pending_approval")
            if pending:
                call_id = pending["action"].get("call_id")
                if state["displayed_approval"] != call_id:
                    print("\nAI proposes this Forth program:")
                    print(f"Purpose: {pending['purpose']}\n---\n{pending['source']}\n---")
                    state["displayed_approval"] = call_id
                prompt = "Run it? Type yes, no, or cancel (other Forth lines will queue): "
            elif state["queued"]:
                raw_input = state["queued"].popleft()
                _process_one_line(vm, raw_input, state)
                continue
            else:
                prompt = "... " if state["in_code_block"] or vm.compiling else "> "
            raw_input = input(prompt)

            # Strip bracketed paste escape sequences if present
            clean_input = re.sub(r"\x1b\[20[01]~", "", raw_input)
            clean_input = clean_input.replace("\r\n", "\n").replace("\r", "\n")

            # Support pasting multiple lines in a single paste burst
            lines = clean_input.split("\n")
            for line in lines:
                pending = vm.host.get("ai_pending_approval")
                if pending:
                    choice = line.strip().casefold()
                    if choice in {"yes", "y"}:
                        vm.host["ai_approval_result"] = True
                    elif choice in {"no", "n"}:
                        vm.host["ai_approval_result"] = False
                    elif choice in {"cancel", "ai-cancel"}:
                        task = state.get("ai_task")
                        try:
                            ai_bridge.cancel_turn()
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
                        if line.strip():
                            state["queued"].append(line)
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
                    state["queued"].append(line)
                else:
                    _process_one_line(vm, line, state)

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
                    ai_bridge.cancel_turn()
                except Exception as err:
                    print(f"Could not cancel remote turn: {err}")
                task = state.get("ai_task")
                if task:
                    task.cancel()
                state["ai_task"] = None
                vm.host.pop("ai_pending_approval", None)
                vm.host.pop("ai_approval_result", None)
                state["displayed_approval"] = None
            state["in_code_block"] = False
            state["code_buffer"] = []
            if vm.compiling:
                vm._discard_definition()
        except (EOFError, SystemExit):
            print("\nbye")
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
