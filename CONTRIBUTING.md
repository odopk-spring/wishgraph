# Contributing to WishGraph

WishGraph welcomes focused bug reports, compatibility evidence, documentation
improvements, and bounded code changes.

## Before opening a change

1. Search existing issues.
2. Describe the user-visible problem and affected host boundary.
3. Keep product decisions, runtime behavior, and documentation synchronized.
4. Do not weaken exact authorization, immutable evidence, or honest host fallback
   behavior to make a test pass.

## Local validation

WishGraph requires Git and Python 3.9+ and has no third-party Python dependency.

```bash
python -m unittest discover
python -m py_compile skills/wishgraph/assets/hooks/*.py skills/wishgraph/scripts/install_project_hooks.py
python skills/wishgraph/scripts/benchmark_hooks.py --enforce
```

On Windows, pass the Python file paths explicitly because PowerShell does not
expand the `*.py` wildcard for Python.

Installer changes should be tested on both Bash and Windows PowerShell. Runtime
changes must update `runtime-manifest.json`, increment `runtime_version`, and
preserve the previous version fingerprints so existing projects can upgrade
safely.

## Pull requests

- Explain the intent, scope, non-goals, validation, and residual risk.
- Add regression tests for behavior changes.
- Keep English and Simplified Chinese user-facing documents aligned when the
  affected surface exists in both languages.
- Avoid unrelated formatting or generated-file churn.
- Contributions are provided under the repository's PolyForm Noncommercial
  License unless a separate written agreement applies.

Security reports follow [SECURITY.md](SECURITY.md), not public issues.
