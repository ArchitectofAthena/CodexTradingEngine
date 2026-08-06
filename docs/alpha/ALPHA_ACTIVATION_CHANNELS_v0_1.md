# CodexTradingEngine Alpha Activation Channels v0.1

## Alpha promise

CodexTradingEngine is alpha-testable when an operator can inspect Gate 1A
readiness, obtain a bounded status surface, run the deterministic offline
research fixture, verify the focused alpha organs, and reproduce a
content-addressed acceptance receipt.

```text
ingest
→ renew
→ regenerate
→ verify
→ compost
→ repeat
```

The alpha front door composes existing organs. It does not add automatic network
capture, wallet access, signing, transactions, execution, flash borrowing,
charity transfer, or capital movement.

## One front door

From a source checkout:

```bash
python codex channels
python codex doctor
python codex status
python codex demo
python codex accept
```

After editable installation, the same surface is available as:

```bash
codex channels
codex doctor
codex accept
```

On POSIX systems you may also run:

```bash
chmod +x codex
./codex accept
```

The recursive lifecycle is directly named:

```bash
python codex ingest
python codex renew
python codex regenerate
python codex compost
python codex repeat
```

`compost` is dry-run by default. With `--apply`, it removes only the dedicated
`artifacts/alpha-activation/` tree.

## Channels

### 1. Local CLI

```bash
python codex doctor
python codex status
python codex demo
python codex verify
```

`doctor` and `status` explain independent readiness and lock states. `demo` uses
the deterministic built-in local route fixture. `verify` runs the focused alpha
tests; `verify --full` runs the complete non-live suite.

### 2. Gate 1A public-testnet read-only observation

This channel is explicit, reviewed, and bounded. It never runs automatically
from `codex accept`.

```text
public testnet observation
→ bounded capture
→ offline replay
→ reviewed local draft
→ local simulation
→ alpha report
```

Follow:

```text
docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md
```

Gate 1A requires no wallet, seed phrase, signing key, transaction, or capital.
Gate 1B and every later gate remain locked.

### 3. Deterministic offline simulation

```bash
python codex demo
```

Outputs:

```text
artifacts/alpha-activation/demo/research-report.json
artifacts/alpha-activation/demo/research-report.md
```

The fixture may show modeled positive edge. That is test evidence, not a promise
of recurrence or permission to trade.

### 4. SpiralBloom MCP stdio membrane

Recommended sibling layout:

```text
$HOME/src/
  spiralbloom-os/
  CodexTradingEngine/
```

Start the membrane from SpiralBloom:

```bash
cd "$HOME/src/spiralbloom-os"
SPIRALBLOOM_ROOT="$HOME/src/spiralbloom-os" \
CODEX_TRADING_ENGINE_ROOT="$HOME/src/CodexTradingEngine" \
python tools/spiralbloom_mcp_server_v0_1.py
```

The stdio JSON-RPC surface provides reviewed introspection, validation, and
proposal construction. It does not expose signing, broadcasting, order
submission, process control, scheduling, wallets, or capital movement.

### 5. SSH / Termius

Codex runs on the Android or workstation host. An iPad using Termius is the
remote console.

For a Termux host:

```bash
pkg install openssh
passwd
sshd
whoami
```

Termux normally listens on port `8022`:

```bash
ssh -p 8022 <termux-user>@<android-address>
```

For a workstation, use its SSH service, normally port `22`.

Use a trusted LAN or private VPN. Do not expose SSH directly to the public
internet. Codex has no browser service of its own; the terminal session is the
channel. BloomHUD can be reached through SpiralBloom's separate loopback SSH
tunnel.

### 6. GitHub evidence lane

GitHub carries:

- ordered source transitions;
- Python 3.11 and 3.13 CI;
- deterministic receipts;
- alpha report issue forms;
- review and explicit human promotion.

A green workflow is evidence, not execution authority.

## Platform setup

### Termux / Android

```bash
pkg update
pkg install git python rust
mkdir -p "$HOME/src"
cd "$HOME/src"
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

python -m pip install --upgrade pip
python -m pip install -e '.[test]'

python codex accept
```

Rust is optional for the basic alpha acceptance but enables the isolated exact
verifier lanes. Missing Rust may produce a warning rather than false success.

### Linux

```bash
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python codex accept
```

### macOS

Use the Linux sequence with a current Python from Homebrew, pyenv, or the
official installer:

```bash
python3 codex accept
```

Install Rust only when testing the exact verifier lanes.

### Windows PowerShell

```powershell
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
Set-Location CodexTradingEngine
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python codex accept
```

The `python codex ...` form is portable and does not depend on executable bits.

## Paired alpha acceptance

```bash
cd "$HOME/src/spiralbloom-os"
python spiralbloom-alpha accept

cd "$HOME/src/CodexTradingEngine"
python codex accept
```

Only after both local receipts report `READY` should the operator open the MCP
membrane for joint introspection.

## Acceptance result

`python codex accept` performs:

1. Gate 1A doctor;
2. alpha status and source-eligibility check;
3. deterministic offline research demo;
4. focused alpha test suite;
5. content-addressed receipt emission.

Receipt path:

```text
artifacts/alpha-activation/codex-alpha-acceptance.json
```

`READY` means those research and review surfaces passed at the recorded commit.
It does not mean production-ready, profitable, mainnet-enabled, or authorized to
move value.

## Boundary

```text
alpha ready != production ready
testnet observation != executable quote
positive fixture edge != expected profit
proposal != order
receipt != permission
MCP access != authority
human promotion remains required
```
