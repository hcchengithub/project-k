# Project K Python Forth quick reference

Curated from `docs/manual-py.md`, `docs/projectk_pause.md`, and the live `base.f` dictionary.

## Input and definitions

- Enter a word or number at the REPL prompt; values are pushed onto the data stack.
- `: square dup * ;` defines a colon word. `12 square` leaves `144` on the stack.
- `words` lists available names; `words <terms>` filters names. `help <terms>` searches word help and comments. `see <name>` displays documentation and a word definition.
- `code <name> ... end-code` defines a Python-host word. Python names used in that code come from the VM host environment.
- `s" text"` pushes a string. `(ai)` consumes a string and pushes the AI response.

## VM tasks

Project K evaluates each input as a resumable `Task`. A host word can yield `vm.pause()` and later continue with `Task.resume()`. `Task.cancel()` closes a paused continuation, but it does not roll back work already performed. AI function calls therefore use the REPL's explicit approval boundary; cancellation is not an undo operation.

## Python bridge and side effects

`py:` and `py>>` are powerful host bridges, not sandboxes. Depending on the expression, Forth can interact with Python modules, files, processes, and other local resources. The AI CLI runs approved Forth in the active local VM and reports the actual output and resulting data stack. Review the complete proposal before approving it.

## AI words

- `ai: <prompt>` sends the rest of the REPL line to the current Agents API session.
- `(ai) ( prompt-string -- response-string )` asks from the stack and pushes the response.
- `ai-status` reports the saved local session ID; `ai-new` forgets that ID so the next request creates a new session.
- At an execution approval prompt, enter `yes`, `no`, or `cancel`. Other entered Forth lines wait in a FIFO queue until the AI task ends.
