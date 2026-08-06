# CodexTradingEngine Cross-Platform Operator Runbook v0.2

## Purpose

Provide one explicit operator path for the four supported surfaces chosen by the Architect:

1. **Android local host** through Termux;
2. **PC local host** through a Linux or UNIX terminal;
3. **Mac local host** through Terminal;
4. **Apple mobile remote console** through Termius SSH on iPhone or iPad.

```text
install prerequisites
→ obtain or update repository
→ enter isolated Python environment where supported
→ run doctor
→ run bounded alpha acceptance
→ inspect receipt
→ stop or disconnect cleanly
```

CodexTradingEngine remains a simulation-first and Gate 1A read-only research system. These instructions do not enable wallets, signing, transactions, flash liquidity, charity transfers, mainnet telemetry, or capital movement.

## Shared repository layout

Use the same sibling layout on every host:

```text
$HOME/src/
  CodexTradingEngine/
  spiralbloom-os/
```

The canonical Codex checkout path is:

```text
$HOME/src/CodexTradingEngine
```

## Shared operator commands

Run these from the repository root:

```bash
python codex channels
python codex doctor
python codex status
python codex demo
python codex verify
python codex accept
```

Useful lifecycle commands:

```bash
python codex ingest
python codex renew
python codex regenerate
python codex compost
python codex repeat
```

`compost` is dry-run by default. It is bounded to `artifacts/alpha-activation/`.

---

## 1. Android local host through Termux

### First installation

```bash
pkg update
pkg upgrade
pkg install git python rust openssh

mkdir -p "$HOME/src"
cd "$HOME/src"
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

python -m pip install --upgrade pip
python -m pip install -e '.[test]'

python codex doctor
python codex accept
```

Rust is optional for the basic alpha path but is required for the isolated exact-verifier lanes. The doctor must report its origin honestly rather than treating an unexplained binary as trusted.

### Existing checkout update

```bash
cd "$HOME/src/CodexTradingEngine"
git status --short
git pull --ff-only
python -m pip install -e '.[test]'
python codex doctor
python codex accept
```

Do not use `git reset --hard`, force-pull, or destructive cleanup as an ordinary update procedure.

### Termux notes

- Termux uses `$HOME`, not a desktop Linux home path copied from another device.
- The expected checkout is `$HOME/src/CodexTradingEngine`.
- Do not depend on `systemd` or desktop service managers.
- Keep generated alpha artifacts inside the repository's declared artifact paths.
- Store Git credentials in a credential manager or SSH agent, never in tracked files.

---

## 2. PC local host through Linux or UNIX terminal

Install Git, Python 3.11 or 3.13, the Python virtual-environment package, and Rust through the host operating system's package manager.

### First installation

```bash
mkdir -p "$HOME/src"
cd "$HOME/src"
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'

python codex doctor
python codex accept
```

### Existing checkout update

```bash
cd "$HOME/src/CodexTradingEngine"
. .venv/bin/activate
git status --short
git pull --ff-only
python -m pip install -e '.[test]'
python codex doctor
python codex accept
```

### Shell portability

- Commands target POSIX-compatible shells.
- Use `python3` instead of `python` until the virtual environment is active when the host does not map `python` to Python 3.
- Do not run the alpha workflow as root.

---

## 3. Mac local host through Terminal

Use a current Python 3.11 or 3.13 installation. Homebrew is one supported prerequisite path:

```bash
brew install git python rust
```

### First installation

```bash
mkdir -p "$HOME/src"
cd "$HOME/src"
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'

python codex doctor
python codex accept
```

### Existing checkout update

```bash
cd "$HOME/src/CodexTradingEngine"
. .venv/bin/activate
git status --short
git pull --ff-only
python -m pip install -e '.[test]'
python codex doctor
python codex accept
```

The Mac runs Codex locally. Termius is not required for this lane.

---

## 4. Apple mobile remote console through Termius SSH

An iPhone or iPad does **not** run this repository locally in this architecture. Termius connects to an Android, Linux/UNIX, or Mac host that already contains the checkout.

### A. Prepare an Android Termux host

On Android:

```bash
pkg install openssh
passwd
sshd
whoami
```

Termux normally exposes SSH on port `8022`.

Record:

```text
address: Android device LAN or private-VPN address
username: output of whoami
port: 8022
```

### B. Prepare a PC or Mac host

Enable the host operating system's SSH service and record:

```text
address: host LAN or private-VPN address
username: host account name
port: 22 unless deliberately changed
```

### C. Create the Termius host entry

In Termius, create a host using:

```text
Address: host LAN or private-VPN address
Username: host account name
Port: 8022 for Termux, normally 22 for PC or Mac
Authentication: SSH key preferred; password permitted only when deliberately configured
```

Do not place repository tokens, wallet secrets, seed phrases, or private keys in Termius snippets or tracked files.

### D. Operate Codex after connecting

For an Android Termux host:

```bash
cd "$HOME/src/CodexTradingEngine"
python codex doctor
python codex status
python codex accept
```

For a PC or Mac host using the virtual environment:

```bash
cd "$HOME/src/CodexTradingEngine"
. .venv/bin/activate
python codex doctor
python codex status
python codex accept
```

Codex has no browser service in this lane, so no port forward is required for Codex itself.

### E. Disconnect cleanly

After the command completes and the receipt is inspected:

```bash
exit
```

Use a trusted LAN or private VPN. Do not expose SSH directly to the public internet.

---

## Paired operation with SpiralBloom OS

Run both acceptance paths independently before opening the cross-repository membrane:

```bash
cd "$HOME/src/spiralbloom-os"
python spiralbloom-alpha accept

cd "$HOME/src/CodexTradingEngine"
python codex accept
```

Then start the reviewed MCP stdio membrane from SpiralBloom:

```bash
cd "$HOME/src/spiralbloom-os"
SPIRALBLOOM_ROOT="$HOME/src/spiralbloom-os" \
CODEX_TRADING_ENGINE_ROOT="$HOME/src/CodexTradingEngine" \
python tools/spiralbloom_mcp_server_v0_1.py
```

```text
Codex acceptance != SpiralBloom acceptance
MCP access != execution authority
cross-repository visibility != repository mutation
```

## Recovery table

| Symptom | Safe response |
|---|---|
| `python` is missing | Use `python3` before activating the virtual environment. |
| Editable install is stale | Re-run `python -m pip install -e '.[test]'`. |
| Dirty working tree | Inspect `git status --short`; do not erase changes automatically. |
| Rust warning | Install or verify Rust, then rerun `python codex doctor`. |
| Unexplained verifier binary | Treat as HOLD; rebuild from reviewed source or verify its declared digest. |
| Termius cannot connect | Confirm SSH is running, address and port are correct, and both devices share the trusted network or VPN. |
| Acceptance fails | Run `python codex doctor`, then `python codex verify` before retrying. |

## Acceptance evidence

A successful platform rehearsal should record:

```yaml
platform: termux_android | linux_unix | macos_terminal | apple_termius_ssh
repository_path: absolute_path
source_commit: git_commit_sha
python_version: string
rust_origin: verified | warning | not_required
operator_command: python codex accept
result: READY | READY_WITH_WARNINGS | HOLD
receipt: artifacts/alpha-activation/codex-alpha-acceptance.json
```

`READY` proves only that the bounded alpha research and review surfaces passed at the recorded commit.

## Boundary

```text
remote terminal != remote authority
SSH access != wallet access
alpha ready != production ready
receipt != permission
testnet observation != executable quote
human promotion remains required
```
