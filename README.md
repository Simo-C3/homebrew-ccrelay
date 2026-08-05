# ccrelay

`ccrelay` (Codex-Copilot Relay) is a loopback-only LiteLLM proxy server that
routes Codex requests to LiteLLM's `github_copilot` provider. It does not wrap
or launch Codex.

```text
Codex -> 127.0.0.1 LiteLLM /v1/responses -> GitHub Copilot Chat API
```

> [!WARNING]
> This is an experimental, single-user proof of concept. LiteLLM's
> `github_copilot` integration is not the official GitHub Copilot SDK: it calls
> the Copilot Chat API using editor-compatible headers. Confirm that this use is
> permitted for your account and organization before running it. Compatibility,
> billing attribution, and account safety are not guaranteed.

## Requirements

- macOS
- Homebrew
- A GitHub account entitled to use GitHub Copilot
- Codex CLI or Codex App

## Install

Install the stable release from the personal tap:

```bash
brew install Simo-C3/ccrelay/ccrelay
ccrelay doctor
```

Apple Silicon macOS uses a prebuilt bottle hosted in this repository's GitHub
Releases. `--HEAD` remains available for testing `main`, but builds LiteLLM from
source and therefore requires Rust and takes substantially longer.

The project pins LiteLLM exactly in `pyproject.toml` and `uv.lock`. Review
dependency changes before upgrading it.

## Authenticate

Trigger the GitHub OAuth device flow:

```bash
ccrelay auth
```

This authenticates directly without sending a model request. OAuth credentials
are stored in the platform-specific `ccrelay/github-copilot` state directory
with user-only directory permissions.

## Models

No model configuration is required. The model selected by Codex is forwarded
unchanged to LiteLLM's GitHub Copilot provider. For example,
`claude-sonnet-4.6` is routed as `github_copilot/claude-sonnet-4.6`.
Availability is determined by the models enabled for the authenticated Copilot
account. Codex's internal `codex-auto-review` model is routed to
`github_copilot/gpt-5.6-sol` because Copilot does not expose that internal model
ID.

## Run the proxy

Run in the foreground:

```bash
ccrelay proxy
```

Run in the background for the current login session:

```bash
ccrelay service run
```

Run in the background and automatically start at login:

```bash
ccrelay service start
```

Homebrew Services manages background processes. The proxy uses a stable
loopback port (`4141` by default) and a persistent local key so GUI applications
can reconnect after a restart.

```bash
ccrelay service status
ccrelay service restart
ccrelay service restart --port 4142
ccrelay service stop
```

Changing the port of a running service requires `service restart`. If the Codex
App integration is enabled, the managed URL is updated at the same time;
restart Codex App afterward.

For a manually configured Codex CLI provider, print the running proxy key in
shell syntax:

```bash
eval "$(ccrelay proxy setenv)"
ccrelay proxy setenv --shell fish
```

## Use Codex App

Start the service, then switch the shared Codex configuration to `ccrelay`:

```bash
ccrelay service start
ccrelay codex-app enable
```

Restart Codex App after switching. Check the current selection with:

```bash
ccrelay codex-app status
```

Switch back to the provider that was selected before `ccrelay`:

```bash
ccrelay codex-app disable
```

The switch updates `$CODEX_HOME/config.toml`, or `~/.codex/config.toml` when
`CODEX_HOME` is unset. Existing comments and unrelated settings are preserved.
The existing `model` setting is never changed, so models selected in Codex keep
working without ccrelay-specific configuration. The previous `model_provider`
value is stored in the private `ccrelay` state directory and restored by
`disable`.

Codex App does not reliably inherit shell environment variables. For that
reason, the local proxy key is written to the managed provider as
`experimental_bearer_token`, and the Codex configuration is restricted to mode
`0600` while enabled. The key only authenticates to the loopback-only proxy.

Disabling uses a three-way merge. Values that still match what ccrelay wrote are
restored or removed, while changes made after enabling are kept and reported.
This includes edits to `model_provider`, the managed provider table, file
permissions, and trailing newlines. An unchanged ccrelay bearer token is removed
from a modified provider table; if a modified token remains, private file
permissions are retained. No force-overwrite option is needed.

Useful commands:

```bash
ccrelay doctor
ccrelay version
```

Set `CCRELAY_LITELLM_BIN` or `CCRELAY_BREW_BIN` to override binary locations.
`CCRELAY_STATE_DIR`, `CCRELAY_CACHE_DIR`, and `CODEX_HOME` override state,
runtime, and Codex configuration directories for testing.

## Verification gate

Do not assume that successful output proves the intended billing route. Before
regular use:

1. Record GitHub Copilot usage and OpenAI API usage.
2. Run one small prompt through Codex.
3. Confirm GitHub Copilot usage increased as expected.
4. Confirm OpenAI API usage did not increase.
5. Exercise a read, file edit, and shell tool call to verify Responses API tool
   compatibility.
6. Stop if GitHub's terms, organization policy, billing attribution, or tool
   compatibility is unclear.

Proxy logs are stored below the platform-specific `ccrelay/service` cache
directory. Logs are redacted for common credential shapes, but verbose logging
should still be treated as sensitive.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy
uv run pytest --cov=ccrelay
```
