# 🖥️ Server Health Monitor (SHM)

A lightweight, production-ready system health monitor for Linux servers. Beautiful terminal UI and email alerts — all from a single `pip install`.

[![PyPI](https://img.shields.io/pypi/v/server-health-monitor)](https://pypi.org/project/server-health-monitor/)
[![Python](https://img.shields.io/pypi/pyversions/server-health-monitor)](https://pypi.org/project/server-health-monitor/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ Features

- **Interactive TUI** — Full-screen terminal dashboard (like `htop`, but for everything)
- **Email Alerts** — Get notified when CPU, memory, disk, or swap cross thresholds
- **Auto-start on Boot** — One command to install as a systemd service
- **Zero Config** — Works out of the box with sensible defaults
- **Lightweight** — Only `psutil`, `PyYAML`, `loguru`, and `pydantic` as core dependencies

---

## 📦 Installation

The **recommended** way to install `monitor` is with [`pipx`](https://pipx.pypa.io/) — it creates an isolated virtualenv behind the scenes and exposes the `monitor` command globally, sidestepping PEP 668's `externally-managed-environment` errors on modern distros.

```bash
pipx install server-health-monitor
pipx ensurepath        # adds ~/.local/bin to PATH (open a new shell after)
```

### Install `pipx` for your distro

<details>
<summary><strong>Debian / Ubuntu / Linux Mint / Pop!_OS</strong></summary>

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Kali Linux</strong></summary>

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Fedora</strong></summary>

```bash
sudo dnf install -y pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>RHEL / CentOS Stream / Rocky / AlmaLinux (9+)</strong></summary>

```bash
sudo dnf install -y python3-pip
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```
</details>

<details>
<summary><strong>Arch Linux / Manjaro / EndeavourOS</strong></summary>

```bash
sudo pacman -S --needed python-pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>openSUSE (Tumbleweed / Leap)</strong></summary>

```bash
sudo zypper install -y python3-pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Alpine Linux</strong></summary>

```bash
sudo apk add pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Void Linux</strong></summary>

```bash
sudo xbps-install -S python3-pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Gentoo</strong></summary>

```bash
sudo emerge --ask dev-python/pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>NixOS</strong></summary>

```bash
nix-env -iA nixpkgs.pipx
pipx ensurepath
```
Or declaratively via `environment.systemPackages = [ pkgs.pipx ];`.
</details>

<details>
<summary><strong>macOS</strong></summary>

```bash
brew install pipx
pipx ensurepath
```
</details>

<details>
<summary><strong>Any distro (fallback — install pipx via pip)</strong></summary>

If your distro doesn't ship `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```
</details>

Then install SHM:

```bash
pipx install server-health-monitor
```

### Alternative: virtualenv + `pip`

If you'd rather not use `pipx`:

```bash
python3 -m venv ~/.venvs/shm
source ~/.venvs/shm/bin/activate
pip install server-health-monitor
monitor
```

> **⚠️ Do not** run `pip install server-health-monitor` system-wide on modern Linux — it will fail with `error: externally-managed-environment` (PEP 668), or pollute your OS Python if forced with `--break-system-packages`.

### Upgrading

```bash
pipx upgrade server-health-monitor
```

### Uninstalling

```bash
pipx uninstall server-health-monitor
```

---

## 🚀 Quick Start

### 1. Launch the TUI

```bash
monitor
```

Navigate with `1`–`6` or `Tab` to switch between views: **Overview**, **Processes**, **Disk**, **Network**, **Alerts**, and **Config**.

### 2. Run as Background Daemon

```bash
monitor --daemon
```

Collects metrics, checks thresholds, and sends email alerts — no UI.

---

## 🔧 Configuration

SHM reads from `config.yaml` in the current directory (or pass `--config /path/to/config.yaml`).

### Default Config

```yaml
thresholds:
  cpu_percent: 85.0
  memory_percent: 85.0
  disk_percent: 90.0
  swap_percent: 80.0

alerts:
  enabled: true
  cooldown_minutes: 5
  log_file: alerts.jsonl

smtp:
  enabled: false
  host: smtp.gmail.com
  port: 587
  username: ""
  password: ""
  from_addr: admin@example.com
  to_addrs:
    - alerts@example.com
  use_tls: true

collection_interval: 5
metrics_log: metrics.jsonl
```

You can also edit the config directly in the TUI — press `6` to go to the **Config** tab, use arrow keys to navigate, `Enter` to edit, and `s` to save.

---

## 📧 Email Alerts Setup

### Gmail (Recommended)

1. **Create a Google App Password**  
   Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) and generate a 16-character app password.

2. **Update your config**:
   ```yaml
   smtp:
     enabled: true
     host: smtp.gmail.com
     port: 587
     username: "you@gmail.com"
     password: "abcd efgh ijkl mnop"    # your app password
     from_addr: "you@gmail.com"
     to_addrs:
       - "alerts@yourcompany.com"
     use_tls: true
   ```

3. **Test it** — Set `cpu_percent: 1.0` temporarily and run:
   ```bash
   monitor --daemon
   ```
   You should receive an email within seconds.

> **Important:** The TUI (`monitor`) is display-only. Email alerts are sent by the **daemon** (`monitor --daemon`) or the **systemd service**.

---

## 🔄 Auto-Start on Boot (systemd)

Install SHM as a system service so the alerting daemon starts automatically on every boot:

```bash
sudo monitor --install
```

This will:
- Copy a default config to `/etc/shm/config.yaml`
- Register and enable a `shm` systemd service
- Start the daemon immediately

### After Installation

```bash
# Edit config (set your SMTP credentials, thresholds, etc.)
sudo nano /etc/shm/config.yaml

# Apply changes
sudo systemctl restart shm
```

### Management Commands

| Command | Description |
|---|---|
| `sudo systemctl status shm` | Check if daemon is running |
| `sudo systemctl restart shm` | Restart after config changes |
| `sudo journalctl -u shm -f` | Watch live logs |
| `sudo monitor --uninstall` | Remove the service |

> **Note:** The systemd service runs independently. You can still use `monitor` (TUI) at any time for interactive monitoring.

---

## 🎮 TUI Keyboard Reference

### Global
| Key | Action |
|---|---|
| `1`–`6` / `Tab` | Switch view |
| `Shift+Tab` | Previous view |
| `?` | Show help overlay |
| `q` | Quit |

### Processes View
| Key | Action |
|---|---|
| `↑` `↓` | Select process |
| `/` | Search by name or PID |
| `s` | Cycle sort (CPU → MEM → PID → Name) |
| `k` | Kill selected process (with confirmation) |
| `Esc` | Clear search |

### Config View
| Key | Action |
|---|---|
| `↑` `↓` | Navigate fields |
| `Enter` | Edit field value |
| `s` | Save config to disk |

---

## 📊 What Gets Monitored?

| Category | Metrics |
|---|---|
| **CPU** | Total %, per-core %, load average, temperature (if available) |
| **Memory** | Used/total, percentage, available, cached, buffers, swap |
| **Disk** | All mounted partitions — used/total/free per mount |
| **Network** | RX/TX rates, total bytes, per-interface stats, errors/drops |
| **Processes** | PID, name, user, CPU%, MEM%, status — sortable and searchable |

---

## 📁 File Structure

After running, SHM creates these files in the working directory:

| File | Purpose |
|---|---|
| `config.yaml` | Configuration (thresholds, SMTP, intervals) |
| `metrics.jsonl` | Timestamped metric snapshots (auto-rotated at 10k lines) |
| `alerts.jsonl` | Alert history log |
| `monitor.log` | Application log (rotated at 10 MB) |

---

## 🔍 Troubleshooting

### `monitor: command not found`
If you installed with `pipx`, run `pipx ensurepath` and open a new shell.
If you installed in a venv, activate it first: `source path/to/venv/bin/activate`.

### `error: externally-managed-environment`
This is PEP 668 on Kali / Debian / Ubuntu — `pip install` outside a venv is blocked by the OS. Use `pipx install server-health-monitor` (recommended), or install inside a venv. See the [Installation](#-installation) section.

### Not receiving emails
- Ensure you are running the **daemon** (`monitor --daemon`) or the **systemd service** — the TUI alone does not send emails.
- Verify `smtp.enabled: true` in your config.
- Check that you're using a [Google App Password](https://myaccount.google.com/apppasswords), not your regular password.
- Check logs: `sudo journalctl -u shm -f` or `tail -f monitor.log`.

### Some metrics are missing
Network connection details and listening ports require elevated privileges:
```bash
sudo monitor
```

---

## 🏗️ Development

```bash
# Clone the repo
git clone https://github.com/Jayanth1312/server-health-monitor.git
cd server-health-monitor

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode
pip install -e .

# Run
monitor
```

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Credits

Built by **Jayanth Paladugu** — [GitHub](https://github.com/Jayanth1312)

If you find this useful, give it a ⭐ on GitHub!
