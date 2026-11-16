# Test Assets Specification (Delivery State)

This directory contains the system's built-in quality gate assets. **Delivery replicas do not require running the full grader suite by default** -- the initialization gate is `npm run validate` (read-only, requires no running server). To execute the graders in this directory, follow the configuration table below.

## 1. Test Layers

| Layer | Assets | Execution |
|---|---|---|
| Primary Grading Body (Recorded-Answer Verification) | `grade_*.py` + `exam_case_*_grade.py` | `python tests/run_grade_checks.py` (full suite) or `--fast` (CI subset) |
| Scripted Unit / E2E Tests | `test_*.py`, etc. | `python tests/<file>.py` |

## 2. Path Conventions (Important)

**Repository root is derived dynamically from file location; hardcoding absolute machine paths is prohibited.** `ROOT` in `tests/grade_lib.py` and script entry points follow this rule, supporting environment variable overrides:

| Environment Variable | Purpose | Default |
|---|---|---|
| `LITETASK_REPO` | Target repository root | Repository root derived from `__file__` |
| `LITETASK_BASE_URL` | Service URL accessed by graders | `http://localhost:3000` |
| `LITETASK_DATA_DIR` | Isolated instance data directory | `<REPO_ROOT>/data` |
| `LITETASK_BACKUP_DIR` | Isolated instance backup directory | `<REPO_ROOT>/backup` |
| `LITETASK_SKILL_SOURCE` | Skill specification source | Same as `ROOT` |
| `LITETASK_SKIP_GRADES` / `LITETASK_SKIP_REASON` | Explicit skip switch and rationale for pre-commit | Unset |

> The service port can be modified in `config/site.json` (`port`); set `LITETASK_BASE_URL` synchronously if changing port.

## 3. Execution Prerequisites

- Most graders access an **active running instance** (`npm start`) via HTTP and assert on disk states. Set `LITETASK_DATA_DIR` to an isolated directory to avoid touching real data.
- Certain graders require `git` metadata (commit history, `.gitattributes`, etc.). Initialize git via `git init` in target projects before executing.
- Placeholder paths such as `<PROJECT_DIR>` / `<REPO_ROOT>` / `<TOOLS_DIR>` are examples, not literal paths.

## 4. Grading Verdict Semantics

The `Checker` in `tests/grade_lib.py` emits structured verdicts:

| Verdict | Meaning | Counted as Failure |
|---|---|---|
| `PASS` | All assertions satisfied | No |
| `FAIL` | Assertion failed; reflects product defect | Yes |
| `PARTIAL` | Partially satisfied; gaps recorded | Yes (incomplete) |
| `BLOCKED` | Prerequisites unsatisfied (service, dependency, or permissions missing) | No; requires environment setup |
| `SKIP` | Explicitly skipped (`LITETASK_SKIP_GRADES` + rationale, or missing dependency) | No |
| `retired()` | Item retired; excluded from statistics | No |

## 5. Legacy Graders

The following graders verify declarations from early multi-repo and task scheduler architectures. In the standalone repository, paths are parameterized:

| File | Legacy Structure Dependency |
|---|---|
| `grade_local_git_baseline.py` | Local git repository status |
| ~~`grade_m3_skill_junction.py`~~ | **Retired**: Removed with legacy junction layout |
| `grade_precommit_gate.py` | Local pre-commit hook installation |
| `grade_server_autostart.py` | Windows scheduled task `LiteTaskServerEnsure` |
| `grade_eol_guard.py` | Binary EOL and encoding guard |
