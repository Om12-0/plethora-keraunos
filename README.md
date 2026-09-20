<p align="center">
  <img src="assets/keraunos.png" width="128" height="128" alt="Plethora Keraunos Icon" />
</p>

<h1 align="center">Plethora Keraunos</h1>

<p align="center">
  <strong>Offline, Deterministic, Git-Backed Declarative Windows Orchestrator</strong>
</p>

<p align="center">
  <a href="https://github.com/Om12-0/plethora-keraunos/releases"><img src="https://img.shields.io/badge/version-1.0.0-8B5CF6.svg" alt="Version 1.0.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License MIT"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4.svg" alt="Platform Windows">
  <img src="https://img.shields.io/badge/LLM--Free-100%25%20Offline-emerald.svg" alt="100% Offline">
</p>

---

## ⚡ Overview

**Plethora Keraunos** is a lightweight, zero-LLM system orchestrator designed for Windows 10 and 11. It brings modern Linux/macOS declarative configuration management to Windows with zero cloud dependencies, instant deterministic execution, and full Git synchronization.

### ✨ Key Features
- **100% Offline Intent Compiler:** RapidFuzz-powered natural phrasing parser that handles conversational filler, app aliases, and system settings offline.
- **Git-Native State Store:** Version control your system state with automated commits, pull/push sync, and drift inspection.
- **Unified WinGet & Registry Management:** Install apps, configure registry tweaks, manage developer environments, and sweep updates in one cohesive state model.
- **Minimalist Electric Purple UI:** Frameless PySide6 GUI with interactive natural prompt cards, deep Windows engine preferences drawer, and diff preview.
- **Hardened Windows Execution:** Smart UAC elevation gating, `run_elevated_powershell`, shell refresh, and DSC Exporter integration.

---

## 📦 Installation & Download

Download the ready-to-use Windows Installer from the **[Releases](https://github.com/Om12-0/plethora-keraunos/releases)** page:
- **Installer:** `Plethora-Keraunos-Setup-1.0.0.exe`

Or install manually via CLI:
```cmd
git clone https://github.com/Om12-0/plethora-keraunos.git
cd plethora-keraunos
pip install -r requirements.txt
python keraunos.py ui
```

---

## 🚀 Quick Command Cheatsheet

### 💻 Graphical User Interface
Launch the frameless desktop view:
```cmd
keraunos ui
```

### 🛠️ CLI Operations
```cmd
# Inspect current system status & drift
keraunos status

# Natural language compiler preview
keraunos plan "install git, vscode, dark mode, enable developer mode"

# Apply pending declarative state
keraunos apply

# Synchronize Git repository with remote
keraunos sync

# Update all installed WinGet applications
keraunos plan "update all apps"
```

---

## ⚙️ Configuration & Architecture

Keraunos stores its declarative configuration state in Git. All registry modifications, winget manifests, and shell preferences are stored deterministically as pure Python state structures and exported optionally to PowerShell DSC.

- **`keraunos/compiler.py`**: Offline Fuzzy & Polarity Intent Engine.
- **`keraunos/catalog.py`**: WinGet package alias lookup dictionary (~245 packages).
- **`keraunos/executor.py`**: Windows state applicator & elevation manager.
- **`keraunos/ui/`**: PySide6 UI views and Electric Purple stylesheet.

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.
