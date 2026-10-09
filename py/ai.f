\ Project K AI words are registered by ai_bridge.install(vm) during REPL startup.
\ This file documents the stable Forth-facing interface and its stack effects.
\
\ ai: <prompt> ( -- )
\   Send the rest of this input line to the saved Agents API session.
\   While the agent works, its local Forth execution proposal pauses the VM
\   until the REPL receives trust/yes/no/cancel input from the user.
\   Trust approves later AI programs for this Forth process only.
\
\ (ai) ( prompt-string -- response-string )
\   Ask the current agent with a string from the data stack. Local Forth
\   proposals still pass through the REPL's approval prompt.
\
\ ai-status ( -- )  Display the active session ID and local history count.
\ ai-new    ( -- )  Start a fresh conversation on the next AI request; keep history.
\ ai-sessions ( -- ) List remote sessions, newest first; numbers select entries.
\ ai-session ( n -- ) Show session details.
\ ai-use ( n -- ) Select a remote session for follow-up chat.
\ ai-transcript ( n -- ) Show user/assistant text for a session.
\ ai-items ( n -- ) Show all session items, including tool interactions.
\ ai-containers ( -- ) List hosted environments associated with remote sessions.
\ ai-container ( n -- ) Show hosted environment details from the latest list.
\ ai-cleanup ( n -- ) Delete a remote session after explicit confirmation.
\ ai-confirm ( -- ) Require approval for each AI Forth program again.
\ ai-cancel ( -- )  Cancel the active Agents API turn.
\
\ The leading backslash is Project K's line-comment word. The host bridge
\ defines the executable implementations so it can pause and resume Tasks.

: ai: (ai-line) ; immediate
