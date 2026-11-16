# Quality Gates and Verification

Lite ADLM maintains an automated grading and test verification harness to guarantee that concurrent operations, line endings, security boundaries, and schema integrity remain uncompromised across platforms.

---

## 1. Quality Gate Architecture

The test harness separates fast local checks from full verification passes:

| Test Suite | Discovery | Execution | Budget / Coverage |
|---|---|---|---|
| **Fast CI Subset** | `tests/run_grade_checks.py --fast` | Automated pre-commit hook (`scripts/precommit_grades.py`) | 13 core graders · < 300s budget |
| **Full Grading Body** | `tests/run_grade_checks.py` | Full pre-release regression check | 41 graders · 880+ assertions |
| **Unit Test Layer** | `tests/test_*.py` | Isolated component tests | CLI force, unlink boundaries, conflict diff |
| **Init Validation** | `npm run validate` | Read-only configuration sanity checker | Zero-drift verification for `categories.json` & anchors |

---

## 2. Running Quality Gates

```bash
# Run the fast grading subset (13 core graders)
python tests/run_grade_checks.py --fast

# Run the complete grading test suite
python tests/run_grade_checks.py

# Run specific graders matching a substring
python tests/run_grade_checks.py --only schema

# Run the read-only package validator
npm run validate
```

> **Note**: Graders that test live HTTP APIs require a running board server instance on port 3000 (`npm start`). File-mode graders run completely offline and independently.

---

## 3. Core Grader Checklist

Key automated graders include:

- `grade_eol_guard.py`: Binary assertion verifying that every tracked source file contains pure LF line endings with zero CRLF sequences and no UTF-8 BOM.
- `grade_item_schema.py`: Strict schema validation ensuring invalid types, missing titles, or out-of-range enums are rejected.
- `grade_b3_concurrency_core.py`: Validates that optimistic locking (`baseRev`) correctly catches concurrent write races and emits `409 CONFLICT`.
- `grade_p0_path_isolation.py`: Verifies path traversal protections and directory whitelisting.
- `grade_size_budget.py`: Pinning file size budgets across all backend modules.
- `grade_local_git_baseline.py`: Verifies clean git repository state and backup sync.
