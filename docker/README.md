# oh-my-wiki Docker reference setup

Optional. Use this if you want:

- Full isolation (backends + auth credentials inside the container)
- Consistent environment across machines
- A clean way to try new backends without installing them on your host

For most users: just install dependencies on your host and use the
**in-skill form factor** (default). See the main README.

## What is included

| Included                  | Not included (user-installed)              |
| ------------------------- | ------------------------------------------ |
| tmux >= 3.0               | codex CLI                                  |
| python3 + pip             | gemini CLI                                 |
| git + ripgrep             | API keys (you supply via each CLI's login) |
| @anthropic-ai/claude-code |                                            |
| opencode-ai               |                                            |

## Quick start

```bash
# 1. Build (run from repo root)
docker compose -f docker/docker-compose.yml build

# 2. Set your vault path
export OMW_VAULT_PATH=/path/to/your/wiki

# 3. Start interactive session
docker compose -f docker/docker-compose.yml run --rm omw

# 4. Inside container: authenticate each backend once
claude /login
# Follow each CLI's own login flow -- OMW never runs login for you.

# 5. Use OMW
omw status                       # check registry/vault state
omw doctor                       # verify the install
# then drive the wiki from your AI session (ingest / query / autoresearch / fact-check)
```

## Adding codex or gemini

The Dockerfile has commented-out install hints. Uncomment or add your own
RUN steps, then rebuild: `docker compose -f docker/docker-compose.yml build --no-cache`

## Data persistence

Auth credentials live in named volumes and persist across restarts.
Dispatch session artifacts live in the `omw-work` volume.
To reset everything: `docker compose -f docker/docker-compose.yml down -v`

## Security

Container runs as non-root (`omwuser`). Auth volumes are not shared.
API keys stay inside the container and its volumes.
