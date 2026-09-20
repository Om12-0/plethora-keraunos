#!/usr/bin/env python3
"""Unified CLI entrypoint for PLETHORA KERAUNOS.

Usage:
    python keraunos.py diff [--state PATH]
    python keraunos.py apply [--state PATH] [--remove-extras] [--elevation raise|warn|relaunch] [--message MSG]
    python keraunos.py drift [--state PATH]
    python keraunos.py compile "dark mode + install 7zip" [--out PATH] [--stdout]
    python keraunos.py export-dsc [--state PATH] [--output configuration.dsc.yaml]
    python keraunos.py history [--limit 20]
    python keraunos.py rollback <sha>
    python keraunos.py remote set <url> [--name origin]
    python keraunos.py remote push [--remote origin] [--branch main]
    python keraunos.py remote pull [--remote origin] [--branch main]
    python keraunos.py remote clone <url> <dest>
    python keraunos.py is-admin
    python keraunos.py scan [--state PATH]
    python keraunos.py presets
    python keraunos.py ui
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from keraunos.compiler import OfflineIntentCompiler
from keraunos.drift import DriftDetector
from keraunos.dsc_exporter import DscExporter
from keraunos.executor import ExecutionEngine
from keraunos.git_store import StateRepository, generate_deterministic_commit_msg
from keraunos.registry_map import list_presets
from keraunos.scanner import scan_text_detailed
from keraunos.schema import KeraunosState
from keraunos.tools import is_admin

DEFAULT_STATE_DIR = Path.home() / ".keraunos"


def _engine(args) -> ExecutionEngine:
    return ExecutionEngine(Path(getattr(args, "state_dir", None) or DEFAULT_STATE_DIR))


def _load_desired(args) -> KeraunosState:
    if getattr(args, "state", None):
        return KeraunosState.from_yaml_file(args.state)
    eng = _engine(args)
    if eng.state_file.exists():
        return KeraunosState.from_yaml_file(eng.state_file)
    print("No state.yaml found — pass --state PATH or run `compile` first.", file=sys.stderr)
    raise SystemExit(2)


def cmd_diff(args) -> int:
    eng = _engine(args)
    desired = _load_desired(args)
    diff = eng.calculate_diff(desired)
    print(eng.render_diff_text(diff))
    return 0


def cmd_apply(args) -> int:
    eng = _engine(args)
    desired = _load_desired(args)
    elevation = getattr(args, "elevation", "raise") or "raise"
    diff = eng.calculate_diff(desired)
    eng.apply_state(desired, remove_extras=args.remove_extras, elevation=elevation)
    try:
        repo = StateRepository(eng.state_dir)
        msg = getattr(args, "message", None) or generate_deterministic_commit_msg(diff)
        sha = repo.commit_evolution(msg)
        print(f"[Git] committed {sha[:8]}")
    except Exception as exc:
        print(f"[Git] commit skipped: {exc}", file=sys.stderr)
    return 0


def cmd_drift(args) -> int:
    desired = _load_desired(args)
    report = DriftDetector.compare(desired)
    print(report.summary())
    return 0 if report.in_sync else 3


def cmd_compile(args) -> int:
    eng = _engine(args)
    base_state = eng.load_current_state()
    compiler = OfflineIntentCompiler()
    state, diagnostics = compiler.compile(args.prompt, base_state=base_state)
    out = Path(args.out) if getattr(args, "out", None) else eng.state_file
    if getattr(args, "stdout", False):
        print(state.to_yaml())
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(state.to_yaml(), encoding="utf-8")
        print(f"Wrote {out}")
        print(eng.render_diff_text(eng.calculate_diff(state)))
    return 0


cmd_generate = cmd_compile


def cmd_history(args) -> int:
    repo = StateRepository(_engine(args).state_dir)
    rows = repo.log(args.limit)
    if not rows:
        print("(no commits yet)")
        return 0
    for r in rows:
        print(f"{r['short']}  {r['date'][:19]}  {r['message']}")
    return 0


def cmd_rollback(args) -> int:
    eng = _engine(args)
    repo = StateRepository(eng.state_dir)
    repo.rollback_to_commit(args.sha)
    print(f"Restored state.yaml from {args.sha[:8]}. Run `apply` to enforce it.")
    return 0


def cmd_scan(args) -> int:
    text = Path(args.state).read_text(encoding="utf-8") if getattr(args, "state", None) else _load_desired(args).to_yaml()
    findings = scan_text_detailed(text)
    if not findings:
        print("No secrets detected.")
        return 0
    print(f"Found {len(findings)} potential secret(s):")
    for f in findings:
        print(f"  line {f.line}: {f.pattern} -> {f.match_preview}")
    return 4


def cmd_presets(_args) -> int:
    for p in list_presets():
        print(p)
    return 0


def cmd_export_dsc(args) -> int:
    desired = _load_desired(args)
    default_out = _engine(args).state_dir / "configuration.dsc.yaml"
    out = Path(getattr(args, "output", None) or default_out)
    DscExporter.export(desired, out)
    print(f"Wrote WinGet DSC manifest -> {out}")
    print(f"Apply natively with: winget configure --file \"{out}\"")
    return 0


def cmd_is_admin(_args) -> int:
    admin = is_admin()
    print("elevated (Administrator)" if admin else "not elevated (standard user)")
    return 0 if admin else 1


def cmd_remote(args) -> int:
    action = args.remote_cmd
    eng = _engine(args)
    if action == "clone":
        StateRepository.clone(args.url, args.dest, branch=getattr(args, "branch", None))
        print(f"Cloned {args.url} -> {args.dest}")
        return 0
    repo = StateRepository(eng.state_dir)
    if action == "set":
        repo.set_remote(args.url, getattr(args, "name", "origin") or "origin")
        print(f"Remote '{getattr(args, 'name', 'origin')}' set -> {args.url}")
        return 0
    if action == "list":
        remotes = repo.list_remotes()
        if not remotes:
            print("(no remotes configured)")
        for name, url in remotes.items():
            print(f"{name}\t{url}")
        return 0
    if action == "push":
        repo.push(getattr(args, "remote", "origin") or "origin",
                  getattr(args, "branch", "main") or "main",
                  set_upstream=getattr(args, "set_upstream", False))
        print(f"Pushed to {getattr(args, 'remote', 'origin')}/{getattr(args, 'branch', 'main')}")
        return 0
    if action == "pull":
        repo.pull(getattr(args, "remote", "origin") or "origin",
                  getattr(args, "branch", "main") or "main")
        print(f"Pulled {getattr(args, 'remote', 'origin')}/{getattr(args, 'branch', 'main')}")
        return 0
    if action == "fetch":
        repo.fetch(getattr(args, "remote", "origin") or "origin")
        print("Fetched.")
        return 0
    raise SystemExit(f"Unknown remote action: {action}")


def cmd_ui(args) -> int:
    from keraunos.ui.app import main
    state_dir = Path(getattr(args, "state_dir", None)) if getattr(args, "state_dir", None) else None
    return main(state_dir)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="keraunos", description="PLETHORA KERAUNOS — declarative Windows orchestrator")
    p.add_argument("--state-dir", default=None, help="State directory (default: ~/.keraunos)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _add_common(s):
        s.add_argument("--state-dir", default=None, help="State directory (default: ~/.keraunos)")
        return s

    s = _add_common(sub.add_parser("diff", help="Show diff between machine state and desired state"))
    s.add_argument("--state", default=None)
    s.set_defaults(func=cmd_diff)

    s = _add_common(sub.add_parser("apply", help="Apply desired state transactionally"))
    s.add_argument("--state", default=None)
    s.add_argument("--remove-extras", action="store_true", help="Uninstall packages not in desired state")
    s.add_argument("--message", default=None)
    s.add_argument("--heal", action="store_true", help=argparse.SUPPRESS)
    s.add_argument("--provider", default=None, help=argparse.SUPPRESS)
    s.add_argument("--model", default=None, help=argparse.SUPPRESS)
    s.add_argument("--prompt", default="", help=argparse.SUPPRESS)
    s.add_argument("--elevation", choices=["raise", "warn", "relaunch"], default="raise",
                   help="How to handle HKLM keys without admin rights (default: raise)")
    s.set_defaults(func=cmd_apply)

    s = _add_common(sub.add_parser("drift", help="Read-only drift scan"))
    s.add_argument("--state", default=None)
    s.set_defaults(func=cmd_drift)

    def _add_compile_args(subp):
        subp.add_argument("prompt", help="e.g. 'dark mode, install 7zip and neovim'")
        subp.add_argument("--out", default=None, help="Output state.yaml path (default: state dir's state.yaml)")
        subp.add_argument("--stdout", action="store_true", help="Print YAML to stdout")
        subp.add_argument("--provider", default=None, help=argparse.SUPPRESS)
        subp.add_argument("--model", default=None, help=argparse.SUPPRESS)
        subp.set_defaults(func=cmd_compile)

    s = _add_common(sub.add_parser("compile", help="Compile natural language prompt into state.yaml"))
    _add_compile_args(s)

    s = _add_common(sub.add_parser("generate", help=argparse.SUPPRESS))
    _add_compile_args(s)
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != "generate"]

    s = _add_common(sub.add_parser("history", help="Show git history of state"))
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_history)

    s = _add_common(sub.add_parser("rollback", help="Restore state.yaml from a commit (then `apply`)"))
    s.add_argument("sha", help="Commit SHA (full or short)")
    s.set_defaults(func=cmd_rollback)

    s = _add_common(sub.add_parser("scan", help="Scan state for embedded secrets"))
    s.add_argument("--state", default=None)
    s.set_defaults(func=cmd_scan)

    s = _add_common(sub.add_parser("presets", help="List known system tweak keys"))
    s.set_defaults(func=cmd_presets)

    s = _add_common(sub.add_parser("export-dsc", help="Export state.yaml to WinGet Configuration DSC YAML"))
    s.add_argument("--state", default=None, help="Input state.yaml (default: state dir's state.yaml)")
    s.add_argument("--output", default=None, help="Output path (default: <state-dir>/configuration.dsc.yaml)")
    s.set_defaults(func=cmd_export_dsc)

    s = _add_common(sub.add_parser("is-admin", help="Report whether this process is elevated"))
    s.set_defaults(func=cmd_is_admin)

    r = _add_common(sub.add_parser("remote", help="Manage the git remote for state sync"))
    rsub = r.add_subparsers(dest="remote_cmd", required=True)

    rs = _add_common(rsub.add_parser("set", help="Set (create/replace) a remote URL"))
    rs.add_argument("url", help="Remote URL, e.g. git@github.com:user/keraunos-state.git")
    rs.add_argument("--name", default="origin")
    rs.set_defaults(func=cmd_remote)

    rs = _add_common(rsub.add_parser("list", help="List configured remotes"))
    rs.set_defaults(func=cmd_remote)

    rs = _add_common(rsub.add_parser("push", help="Push current branch to the remote"))
    rs.add_argument("--remote", default="origin")
    rs.add_argument("--branch", default="main")
    rs.add_argument("--set-upstream", action="store_true")
    rs.set_defaults(func=cmd_remote)

    rs = _add_common(rsub.add_parser("pull", help="Pull a branch from the remote"))
    rs.add_argument("--remote", default="origin")
    rs.add_argument("--branch", default="main")
    rs.set_defaults(func=cmd_remote)

    rs = _add_common(rsub.add_parser("fetch", help="Fetch from the remote without merging"))
    rs.add_argument("--remote", default="origin")
    rs.set_defaults(func=cmd_remote)

    rs = _add_common(rsub.add_parser("clone", help="Clone a remote state repo into a directory"))
    rs.add_argument("url")
    rs.add_argument("dest")
    rs.add_argument("--branch", default=None)
    rs.set_defaults(func=cmd_remote)

    s = _add_common(sub.add_parser("ui", help="Launch the desktop overlay"))
    s.set_defaults(func=cmd_ui)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
