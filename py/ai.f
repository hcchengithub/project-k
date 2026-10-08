\ Project K AI words are registered by ai_bridge.install(vm) during REPL startup.
\ This file documents the stable Forth-facing interface and its stack effects.
\
\ ai: <prompt> ( -- )
\   Send the rest of this input line to the saved Agents API session.
\   While the agent works, its local Forth execution proposal pauses the VM
\   until the REPL receives explicit yes/no/cancel input from the user.
\
\ (ai) ( prompt-string -- response-string )
\   Ask the current agent with a string from the data stack. Local Forth
\   proposals still pass through the REPL's confirmation prompt.
\
\ ai-status ( -- )  Display the locally saved session ID.
\ ai-new    ( -- )  Forget the local session ID; next request creates one.
\ ai-cancel ( -- )  Cancel the active Agents API turn.
\
\ The leading backslash is Project K's line-comment word. The host bridge
\ defines the executable implementations so it can pause and resume Tasks.

: ai: (ai-line) ; immediate
