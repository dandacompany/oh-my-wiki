# Scheduled knowledge maintenance

`omw maint status --exit-code` exits 1 when any page is stale/expired or lint finds
issues. Two ways to run it on a schedule:

## A. Claude Code `schedule` skill (recommended)

Ask Claude: "schedule a daily 9am routine that runs `omw maint status` and, if work
is due, opens the omw menu to triage." The routine runs `omw maint status`, and on
non-empty `nudge` follows `commands/menu.md` (the 노후 정리 path).

## B. launchd / cron (headless notify)

```bash
# crontab -e  — weekday 9am, notify on Telegram when maintenance is due
0 9 * * 1-5  omw maint status --exit-code >/tmp/omw-maint.json \
   && true || ~/.claude/auth/notify-telegram.sh "$(cat /tmp/omw-maint.json)"
```

The `&& true ||` runs the notifier only on exit 1 (work due).

## Harness keeps proposing

The session preamble (`omw recall preamble`, Task 1.2) already injects the same
`유지보수:` nudge at every session start — so even without cron, the agent is
reminded whenever you open the project.
