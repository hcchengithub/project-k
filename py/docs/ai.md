# Project K AI support (Python CLI)

The Python REPL has an optional OpenAI Agents API integration. The bridge uses only the Python standard library; ordinary Forth use does not require a key or network access.

## Configuration

The bridge reads `py/.env` when an AI request starts. An operating-system environment variable takes precedence over a value in `.env`.

```dotenv
OPENAI_API_KEY=your-platform-api-key
PROJECTK_AI_MODEL=gpt-6-astra
PROJECTK_AI_SKILLS_DIR=skills
```

`PROJECTK_AI_MODEL` selects the Agents API model. `PROJECTK_AI_SKILLS_DIR` selects the directory containing `projectk-forth/SKILL.md`; a relative path resolves from the Python directory. The default is `py/skills`. The selected skill is packaged into an inline plugin ZIP when a new session is created. Existing sessions keep their original hosted environment; run `ai-new` after changing the plugin or skill to load the new bundle.

Keep `.env` private. The local bridge sends the API key only as the HTTPS bearer credential. It does not put the key into the plugin, conversation, or tool result. The prompt and resulting conversation are sent to OpenAI's service according to the account's API data controls.

## Forth interface

- `ai: <prompt>` sends the rest of the current line and streams the reply in the terminal.
- `(ai) ( prompt-string -- response-string )` consumes a string and pushes the response, for example: `s" Give me a short greeting" (ai) . cr`.
- `ai-status` displays the saved local session ID, if one exists.
- `ai-new` removes the local session ID. The next AI request creates a new hosted session. It does not delete a remote session.
- `ai-cancel` sends the Agents API cancellation event for an active turn. At the local approval prompt, `cancel` or `ai-cancel` also closes the paused VM task.

The session ID is stored in `py/.ai_session.json`, excluded from Git. It preserves the hosted conversation across REPL restarts, but does not restore the local VM's stack, dictionary, or files.

## Local Forth tools and confirmation

The agent can search the active VM's Forth dictionary. To run a program, it must request `projectk_run_forth`. The REPL refreshes the session's pending actions before displaying the proposal, then checks again before execution. It displays the complete Forth source and its stated purpose. Enter `yes` to execute it, `no` to decline, or `cancel` to cancel the local suspended task. Any other entered Forth lines at this confirmation prompt are queued and run in order after the AI task finishes. If an API result submission fails after local execution, the error reports that the Forth program already ran; inspect the VM before retrying.

Network requests currently run synchronously in the REPL. While the agent is waiting for an API response, the REPL cannot yet accept and queue new input; queueing is available while the local execution confirmation is open.

Approved source runs in the current local VM and can use Project K's Python host bridges. Review it for file, process, and other machine side effects. The bridge returns the actual status, standard output, standard error, and resulting data stack to the agent. Cancellation closes the local task; already completed side effects are not undone.

## Troubleshooting

- **Missing API key:** Add `OPENAI_API_KEY` to `py/.env` or the process environment, then restart the REPL.
- **Invalid key, model, or API access:** Read the Agents API error printed by the REPL; check the Platform project, model access, and API billing/limits.
- **Plugin/skill not found:** Ensure `PROJECTK_AI_SKILLS_DIR` points to a directory containing `projectk-forth/SKILL.md` and that `plugins/projectk-forth/.codex-plugin/plugin.json` is valid JSON.
- **Skill changes do not take effect:** Use `ai-new` and make another request to create a session with a fresh plugin ZIP.
- **Wrong saved conversation:** Use `ai-new` to clear the local session ID. This does not erase the remote session.
- **Network interrupted:** The bridge reports a connection or stream error. Retry the prompt; if the turn's state is unclear, use `ai-status` and `ai-new` to deliberately start a fresh conversation.

## API flow

The bridge creates an Agents API session with an OpenAI-hosted environment and an inline ZIP plugin. It streams session events, answers dictionary function calls locally, and returns function results with their `turn_id` and `call_id`. The session ID alone is persisted locally. No OpenAI SDK is required.
