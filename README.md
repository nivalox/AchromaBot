# Axion

### A full-featured Achroma selfbot written in Python.

> Thanks @LATUFFGUYMAINACC for muting me. You're gonna get demoted for this.

## Features

AchromaBot provides chat automation, account management, profile customization, AI integration, and message monitoring.

### Chat Commands

| Command | Description |
|---|---|
| `?ping` | Shows the current ping. |
| `?stats` | Shows phone and Termux statistics. |
| `?snipe` | Shows the latest deleted message in this channel. |
| `?csnipe` / `?clearsnipe` | Clears sniped messages. |
| `?echo <text>` | Sends the specified text. |
| `?ai <question>` | Asks Gemini a question and returns a plain-text answer. |
| `?typing on/off` | Toggles the typing indicator. |
| `?silenttyping on/off` | Toggles cancellation of your typing indicator. |
| `?autoreact on/off` | Toggles automatic reactions to new messages. |
| `?autoreact emoji <e>` | Changes the reaction emoji. |
| `?autoreact users <names/all>` | Configures which users trigger reactions. |
| `?autoreply on/off` | Toggles automatic replies to incorrect commands and unauthorized interactions. |
| `?channel` | Lists watched channels. |
| `?channel add/remove <name>` | Adds or removes watched channels. |
| `?dm <user ID, username or DM name>` | Starts watching a DM. |
| `?profile name/user/bio <text>` | Changes your profile information. |
| `?profile show` | Displays your current profile. |
| `?grant <user> [commands/all]` | Grants another user permission to use selected commands. |
| `?revoke <user> [commands]` | Revokes previously granted command permissions. |
| `?grants` | Lists users who have been granted commands. |
| `?signin` / `?signing` | Signs in through the terminal and refreshes the session. |
| `?signup` | Creates an account through terminal input. |
| `?quickacc [-c pass]` | Creates a random account, signs in, and saves it. |
| `?creds` | Displays credits. |
| `?help` | Lists available commands. |
| `?help <command>` | Explains a specific command. |

### Terminal Commands

These commands are available directly in the terminal.

| Command | Description |
|---|---|
| `accounts` | Lists saved accounts. |
| `switch <name>` | Switches to a saved account. |
| `addaccount` | Signs into another account and switches to it. |
| `removeaccount <name>` | Removes a saved account. |
| `aikey` | Sets the Gemini API key through hidden input and saves it to `secrets.json`. |
| `aimodel [name]` | Shows or changes the Gemini model. |
| `aimodels` | Lists models available to your API key. |
| `use <channel>` | Sets the channel used by terminal commands and echo. |
| `quit` | Stops the bot. |

**Note:** Every chat command also works in the terminal, with or without the `?` prefix.

## Installation

Axion supports:

- Android (Termux)
- Windows
- Linux

### 1. Termux (Android)

Install Python and Git:

```bash
pkg update && pkg upgrade -y
pkg install python git -y
```

Clone AchromaBot:

```bash
git clone https://github.com/nivalox/AchromaBot.git AchromaBot
cd AchromaBot
```

Install dependencies:

```bash
pip install requests
```

Run Axion:

```bash
python main.py
```

### 2. Windows

Install Python and Git using Winget:

```powershell
winget install Python.Python.3.14
winget install Git.Git
```

Restart your terminal, then clone the repository:

```powershell
git clone https://github.com/nivalox/AchromaBot.git AchromaBot
cd AchromaBot
```

Install dependencies:

```powershell
py -m pip install --upgrade pip
py -m pip install requests
```

Run Axion:

```powershell
py main.py
```

### 3. Linux (Debian / Ubuntu)

Install Python, pip, and Git:

```bash
sudo apt update
sudo apt install python3 python3-pip git -y
```

Clone AchromaBot:

```bash
git clone https://github.com/nivalox/AchromaBot.git AchromaBot
cd AchromaBot
```

Install dependencies:

```bash
python3 -m pip install --user requests
```

Run Axion:

```bash
python3 main.py
```

## Dependencies

AchromaBot uses Python's standard library alongside the following external package:

| Dependency | Purpose |
|---|---|
| `requests` | HTTP requests and API communication |

The following modules are included with Python and require no additional installation:

- `getpass`
- `json`
- `os`
- `collections`
- `platform`
- `random`
- `re`
- `select`
- `shutil`
- `string`
- `sys`
- `subprocess`
- `threading`
- `time`
- `uuid`

## Configuration

### Gemini AI

To configure Gemini:

1. Start AchromaBot.
2. Run `aikey` in the terminal.
3. Enter your Gemini API key through the hidden input.
4. Use `aimodels` to see available models.
5. Use `aimodel <name>` to select a model.

Your API key is stored in `secrets.json`.

## Running Axion

After installation and dependency setup:

```bash
python main.py
```

On systems where Python 3 is invoked separately:

```bash
python3 main.py
```

## Author

**nivalos**

GitHub: https://github.com/nivalox

Made with Python.
