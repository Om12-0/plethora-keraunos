# Multi-Subagent Architecture & Orchestration Directives

## Architecture Overview
The Antigravity controller operates as a primary orchestrator that decomposes complex coding, indexing, and debugging operations into discrete tasks handled by parallel subagents running on Gemini Flash in low-latency (zero/minimal thinking) mode.

---

## 1. SUBAGENT ROLES & TOPOLOGY

| Subagent Name | Default Model | Mode / Thinking | Primary Responsibilities | Write Access |
|---|---|---|---|---|
| **`Subagent-Explorer`** | `flash` (`gemini-2.5-flash`) | Low (`thinkingBudget: 0`) | Codebase & Environment Scout: Reads directory trees, checks file existences, greps logs, inspects process lists, checks Windows PE headers. Returns raw facts without verbose commentary. | Read-Only |
| **`Subagent-Coder`** | `flash` (`gemini-2.5-flash`) | Low (`thinkingBudget: 0`) | Deterministic Implementer: Takes specific function/class/module specs and writes exact Python/Win32/C++ code. Outputs clean code diffs or complete target files. | Full (Files & Commands) |
| **`Subagent-Tester`** | `flash` (`gemini-2.5-flash`) | Low (`thinkingBudget: 0`) | Validation & Execution Worker: Executes `pytest`, runs build scripts (`pyinstaller`, `iscc`), monitors background task IDs, captures error tracebacks, and reports immediate binary pass/fail status. | Full (Commands) |
| **`Subagent-Reviewer`** | `flash` (`gemini-2.5-flash`) | Low (`thinkingBudget: 0`) | Antivirus & Regression Guard: Verifies PE subsystems (`console=False`), checks `version_info.txt`, inspects Windows API call signatures (`CREATE_NO_WINDOW`), and verifies git staging. | Read-Only |

---

## 2. ORCHESTRATOR WORKFLOW DIRECTIVES

When delegating tasks to subagents, the primary orchestrator must strictly enforce:

### A. Strict Delegation Format
Every subagent dispatch must provide only:
1. **Target File Path(s)**
2. **Single Strict Requirement**
3. **Expected Return Contract** (JSON or code snippet only)

### B. Low-Mode Generation Configuration
Subagent invocations use:
```json
{
  "model": "flash",
  "generationConfig": {
    "temperature": 0.0,
    "thinkingConfig": {
      "thinkingBudget": 0
    }
  }
}
```
Eliminate verbose introductory explanations and closing conversational fluff in subagent prompts and outputs.

### C. Parallel Dispatching & Error Feedback Loop
1. **Concurrent Dispatch**: Dispatch `Subagent-Explorer` and `Subagent-Coder` concurrently when scaffolding modules.
2. **Immediate Test Pipeline**: Trigger `Subagent-Tester` immediately upon file write completion.
3. **Isolated Feedback Loop**: If tests fail, send the isolated stack trace directly to `Subagent-Coder` to fix without restarting the entire conversation context.
4. **Pre-commit Gate**: Run `Subagent-Reviewer` before git staging and finalizing build artifacts.

---

## 3. ACTIVE SUBAGENT DEPLOYMENT PROTOCOL
- Break broad refactoring or multi-file tasks into discrete, independent subagent task items.
- Run long tasks asynchronously using background terminal monitors (`task-<id>`).
- Synthesize all subagent results into a final concise verification report.
