# Project K AI support (Python CLI)

The Python REPL has an optional OpenAI Agents API integration. The bridge uses only the Python standard library; ordinary Forth use does not require a key or network access.

## Configuration

The bridge reads `py/.env` when an AI request starts. An operating-system environment variable takes precedence over a value in `.env`.

```dotenv
OPENAI_API_KEY=your-platform-api-key
PROJECTK_AI_MODEL=gpt-6-astra
PROJECTK_AI_SKILLS_DIR=skills
```

`PROJECTK_AI_MODEL` selects the Agents API model. `PROJECTK_AI_SKILLS_DIR` selects the directory containing `projectk-forth/SKILL.md`; a relative path resolves from the Python directory. The default is `py/skills`. For new sessions, the skill and Forth reference are included in agent instructions because `environment.type: "none"` has no filesystem for loading a plugin. New sessions do not provision an OpenAI-hosted sandbox/container. Existing sessions keep their original configuration.

Keep `.env` private. The local bridge sends the API key only as the HTTPS bearer credential. It does not put the key into the plugin, conversation, or tool result. The prompt and resulting conversation are sent to OpenAI's service according to the account's API data controls.

## Forth interface

- `ai: <prompt>` sends the rest of the current line and streams the reply in the terminal.
- `(ai) ( prompt-string -- response-string )` consumes a string and pushes the response, for example: `s" Give me a short greeting" (ai) . cr`.
- `ai-status` displays the active session ID and the number of locally indexed sessions.
- `ai-sessions` fetches the remote session list, newest first, and assigns sequence numbers for management words. The displayed sequence is a snapshot; run this again to refresh it.
- `n ai-session` retrieves and displays status, model, environment, timestamps, and token usage for a listed session.
- `n ai-use` makes a listed remote session active so subsequent `ai:` prompts continue that conversation.
- `n ai-transcript` shows only user and assistant text for a listed session.
- `n ai-items` prints all saved API items for a listed session, including tool call and result records.
- `ai-new` clears only the active selection. The next `ai:` request creates a new Agents API session with no hosted sandbox; old sessions remain in the remote list and local index.
- `ai-containers` inspects hosted environments linked to sessions in the latest `ai-sessions` snapshot. It shows environment IDs, session IDs, size, and reported status. This is not a billing meter.
- `n ai-container` shows details for an environment from the latest `ai-containers` list.
- `n ai-cleanup` asks for the exact confirmation `delete`, then removes that remote session and conversation. If it has an old hosted sandbox, deletion requests sandbox cleanup; physical cleanup may continue asynchronously. This cannot be undone. It removes the deleted session from the local index and requires refreshing lists before another numbered operation.
- `ai-cancel` sends the Agents API cancellation event for an active turn. At the local approval prompt, `cancel` or `ai-cancel` also closes the paused VM task.

The active session and a local index of known session IDs are stored in `py/.ai_session.json`, excluded from Git. The remote API remains the source of session details and conversation items. Sessions do not restore the local VM's stack, dictionary, or files. Run `ai-sessions` before numbered session words and `ai-containers` before `n ai-container`.

## Local Forth tools and confirmation

The agent can search the active VM's Forth dictionary. To run a program, it must request `projectk_run_forth`. The REPL refreshes the session's pending actions before displaying the proposal, then checks again before execution. It displays the complete Forth source and its stated purpose. At each approval prompt, `trust` executes the proposal and automatically approves later AI programs for the lifetime of the current Forth process; `yes` executes only this proposal; `no` declines this proposal; and `cancel` cancels this AI task. Run `ai-confirm` to restore per-proposal approval. Trust is held only in memory and resets when the Forth process exits. If an API result submission fails after local execution, the error reports that the Forth program already ran; inspect the VM before retrying.

Network requests currently run synchronously in the REPL. While the agent is waiting for an API response, the REPL cannot yet accept and queue new input; queueing is available while the local execution confirmation is open.

Approved source runs in the current local VM and can use Project K's Python host bridges. Review it for file, process, and other machine side effects. The bridge returns the actual status, standard output, standard error, and resulting data stack to the agent. Cancellation closes the local task; already completed side effects are not undone.

## Troubleshooting

- **Missing API key:** Add `OPENAI_API_KEY` to `py/.env` or the process environment, then restart the REPL.
- **Invalid key, model, or API access:** Read the Agents API error printed by the REPL; check the Platform project, model access, and API billing/limits.
- **Skill not found:** Ensure `PROJECTK_AI_SKILLS_DIR` points to a directory containing `projectk-forth/SKILL.md`.
- **Skill changes do not take effect:** Use `ai-new` and make another request to create a session with fresh instructions.
- **Wrong saved conversation:** Run `ai-sessions`, then select the intended entry with `n ai-use`.
- **Remove a session and request hosted sandbox cleanup:** Run `ai-sessions`, then `n ai-cleanup` and type `delete` only if you intend to permanently remove that session and its conversation.
- **Network interrupted:** The bridge reports a connection or stream error. Retry the prompt; if the turn's state is unclear, use `ai-status` and `ai-new` to deliberately start a fresh conversation.

## API flow

The bridge creates an Agents API session with no execution environment. It includes the Project K skill and reference in the agent instructions. Because `environment.type: "none"` requires initial input, it submits and streams the first prompt during session creation. Later turns subscribe to the session stream before sending input. The bridge answers dictionary and Forth function calls locally, and returns function results with their `turn_id` and `call_id`. The active session and known IDs are persisted locally. No OpenAI SDK is required. Model token usage is still billed at the selected model's API rates; no OpenAI-hosted sandbox/container is provisioned for new sessions.

`ai-containers` derives the environment list from remote sessions and retrieves each linked hosted environment by ID. The separate environments-list endpoint may require prewarming beta access, so this word does not rely on it and may not show environments no longer linked to a listed session. Environment status does not establish billable usage; use the API usage dashboard for charges.
