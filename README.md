# AchromaBot

### A full-featured Achroma selfbot written in Python.

> Thanks @LATUFFGUYMAINACC for muting me. You're gonna get demoted for this.

## Features

AchromaBot provides chat automation, account management, profile customization, and monitoring features.

### Chat Commands

| Command | Description |
|---|---|
| `?ping` | Shows the current ping. |
| `?typing on/off` | Toggles the typing indicator. |
| `?silenttyping on/off` | Toggles cancellation of your typing indicator. |
| `?profile name/user/bio <text>` | Changes your profile information. |
| `?profile show` | Displays your current profile. |
| `?channel` | Lists watched channels. |
| `?channel add/remove <name>` | Adds or removes watched channels. |
| `?dm <user ID, username or DM name>` | Starts watching a DM. |
| `?echo <text>` | Sends the specified text. |
| `?snipe` | Shows the latest deleted message. |
| `?csnipe` / `?clearsnipe` | Clears sniped messages. |
| `?autoreply on/off` | Toggles automatic replies to incorrect commands and unauthorized interactions. |
| `?autoreact on/off` | Toggles automatic reactions to new messages. |
| `?autoreact emoji <e>` | Changes the reaction emoji. |
| `?autoreact users <names/all>` | Configures which users trigger reactions. |
| `?signin` | Signs in through the terminal and refreshes the session. |
| `?signup` | Creates an account through terminal input. |
| `?quickacc [-c pass]` | Creates a random account, signs in, and saves it. |
| `?stats` | Displays phone and Termux statistics. |
| `?creds` | Displays credits. |
| `?help` | Displays the command list. |

### Terminal Commands

| Command | Description |
|---|---|
| `accounts` | Lists saved accounts. |
| `switch <name>` | Switches to a saved account. |
| `addaccount` | Signs into another account and switches to it. |
| `removeaccount <name>` | Removes a saved account. |
| `use <channel>` | Sets the channel used by terminal replies and echo. |
| `quit` | Stops the bot. |

**Note:** Every chat command also works in the terminal, with or without the `?` prefix.

### Message Monitoring

- Deleted message detection.
- Latest deleted message retrieval through `?snipe`.
- Watched-channel management.
- Direct message monitoring.

### Account Management

- Terminal-based authentication.
- Account registration.
- Random account generation.
- Saved account management.
- Account switching.

### Device Compatibility

Designed to run in a Python environment, including Android through Termux.

## Author

**nivalos**

Made with Python.
