<p align="center">
  <img src="assets/keraunos.png" width="128" height="128" alt="Plethora Keraunos Icon" />
</p>

<h1 align="center">Plethora Keraunos</h1>

<p align="center">
  <strong>100% Offline, Deterministic, Git-Backed Declarative Windows Orchestrator</strong>
</p>

<p align="center">
  <a href="https://github.com/Om12-0/plethora-keraunos/releases"><img src="https://img.shields.io/badge/version-1.0.3-8B5CF6.svg?style=flat-square" alt="Version 1.0.3"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License MIT"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4.svg?style=flat-square" alt="Platform Windows">
  <img src="https://img.shields.io/badge/AI-100%25%20Offline%20(SmolLM2)-10B981.svg?style=flat-square" alt="100% Offline AI">
  <img src="https://img.shields.io/badge/execution-Silent%20Zero--CMD-purple.svg?style=flat-square" alt="Silent Execution">
  <a href="https://discord.com/users/thawl3ss"><img src="https://img.shields.io/badge/Discord-thawl3ss-5865F2?style=flat-square&logo=discord&logoColor=white" alt="Discord thawl3ss"></a>
</p>

<p align="center">
  <strong>Maintained & Architected by <a href="https://github.com/Om12-0">@Om12-0</a></strong> • <em>Discord: <code>thawl3ss</code></em>
</p>

---

## ⚡ Overview

**Plethora Keraunos** is a modern, privacy-first declarative system orchestrator designed specifically for **Windows 10 and 11**. It bridges Linux/macOS declarative infrastructure-as-code concepts with the Windows ecosystem: managing applications, system personalization, hardware displays, and environment configurations through natural human language with **zero cloud dependencies** and **full Git versioning**.

---

## ✨ Key Features

### 🧠 Dual-Tier Offline Natural Intent Engine
- **Tier 1 (Sub-millisecond Deterministic):** RapidFuzz token sort matching with strict polarity inversion, theme mutual exclusivity, and conversational noise stripping.
- **Tier 2 (Embedded Local SLM):** Powered by **SmolLM2-135M-Instruct** (~85 MB GGUF) running locally via `llama-cpp-python` with AVX2 CPU inference. Understands colloquial speech and complex multi-clause requests with zero internet access and zero API keys.

### 📦 Multi-Provider Package Management
- **WinGet Ecosystem:** Instant lookup across curated app aliases with **Dynamic Live WinGet Search** fallback for unlisted Microsoft Store and WinGet packages.
- **Chocolatey & Scoop Providers:** Native support for `choco` and `scoop` packages directly inside prompts (`choco install 7zip`, `scoop install neovim`).

### 🖥️ Native Win32 Display & Hardware Engine
- Enumerate connected monitors and dynamically switch primary display outputs using native `user32.ChangeDisplaySettingsExW` and positional coordinate shifting.
- Supports intuitive prompts like *"change primary screen to monitor 1"* or *"switch main display to 2"*.

### ⚡ Silent Zero-CMD In-App Execution
- Background `ApplyWorker` running on dedicated asynchronous `QThread` with real-time status progression.
- Hardened with `CREATE_NO_WINDOW` (`0x08000000`) across all Windows subprocess calls—eliminating distracting black Command Prompt popups and focus interruptions.

### 🔄 Asynchronous GitHub Auto-Updater
- Built-in updater engine (`keraunos/updater.py`) that checks GitHub Releases for new setup packages.
- Download and install updates silently in-place directly from the UI or via natural voice commands like *"check for updates"*.

### 🛡️ Antivirus Hardening & Security
- Embedded Windows PE Version Resource (`version_info.txt`) and GUI subsystem (`PE Subsystem: 2`) preventing false positive heuristic alarms.
- Integrated secret scanner preventing private keys, tokens, or credentials from ever entering declarative configuration files.

### ☁️ Git State Store & Drift Inspection
- Every state change is backed by automatic, human-readable Git commits (`feat(packages)`, `chore(system)`).
- Real-time **Drift Inspection** comparing your live Windows registry and package inventory against your desired state.

---

## 📦 Installation & Download

### Standalone Installer (Recommended)
Download the latest Windows setup executable from the **[GitHub Releases](https://github.com/Om12-0/plethora-keraunos/releases)**:
- **Installer:** `Plethora-Keraunos-Setup-1.0.2.exe`
- Includes: Complete Python runtime, embedded SmolLM2 model (~85 MB), Desktop shortcut, and Start Menu integration.

### From Source (Developer CLI)
```cmd
git clone https://github.com/Om12-0/plethora-keraunos.git
cd plethora-keraunos
pip install -r requirements.txt
python keraunos.py ui
```

---

## 🚀 Usage & Phrasing Examples

### 💻 Graphical Interface
Launch the frameless Electric Purple desktop utility:
```cmd
keraunos ui
```

### 🗣️ Example Everyday Phrasing
Type or speak naturally—Keraunos parses intent seamlessly:
- `"install lightshot, visual studio code, and discord"`
- `"disable light mode and enable compact view in explorer"`
- `"switch primary screen to screen 1"`
- `"choco install git and scoop install ripgrep"`
- `"update all my apps"`
- `"push my configuration state to github"`
- `"check for updates"`

### 🛠️ CLI Operations
```cmd
# Inspect current system configuration & drift
keraunos status

# Preview declarative plan from natural prompt
keraunos plan "install git, vscode, dark mode, disable bing search"

# Apply pending desired state
keraunos apply

# Synchronize Git repository with remote
keraunos sync
```

---

## ⚙️ Architecture & Codebase Map

```
plethora-keraunos/
├── keraunos/
│   ├── compiler.py        # Dual-tier intent compiler (RapidFuzz + SLM router)
│   ├── slm.py             # Embedded SmolLM2-135M local inference engine
│   ├── catalog.py         # WinGet alias catalog & live WinGet search fallback
│   ├── display.py         # Win32 hardware monitor manager (ChangeDisplaySettingsExW)
│   ├── executor.py        # Silent state executor, diff engine, & rollback generator
│   ├── tools.py           # WinGet, Scoop, Chocolatey & Registry subprocess wrappers
│   ├── updater.py         # Asynchronous GitHub auto-updater engine
│   ├── git_store.py       # Git versioning & deterministic commit message builder
│   ├── drift.py           # Live system drift detector
│   ├── schema.py          # Pydantic declarative state model (KeraunosState)
│   └── ui/                # PySide6 frameless application & Electric Purple QSS
├── installer/             # Inno Setup 6 packaging scripts
├── models/                # Local GGUF model storage (SmolLM2-135M)
├── tests/                 # 60+ pytest integration and unit test suite
└── keraunos.spec          # PyInstaller windowed packaging manifest
```

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.
