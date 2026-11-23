# Axion

Run it with `python main.py` (or `python -m axion`). `config.json` and `secrets.json` stay next to `main.py`,
so your existing ones keep working.

```
main.py                 entry point
axion/
  constants.py          version, URLs, default config
  state.py              loaded config + live state
  config.py             saving config / secrets
  registry.py           the command table (@command decorator, help sections, grantable flags)
  context.py            Ctx: what a command handler gets
  dispatcher.py         prefix parsing, permission check, autoreply, running the handler
  poller.py             background Fetcher thread + handling fetched messages, learning users
  terminal.py           typed terminal commands
  bot.py                startup + main loop
  views.py              formatted terminal output
  ui/                   theme, line editor, output helpers, spinner, banner
  net/                  http session, typing loops, ping, voice (join/leave + keepalive)
  features/             snipe, grants, autoreply, accounts, ai, channels, social, linkgen, ...
  commands/             one file per help section (general, messaging, social, ...), each command is a small @command function
  utils/                formatting, system info, @mention parsing
```

To add a command, write a function in `axion/commands/` with `@command("name", args, description, section=...)`.
