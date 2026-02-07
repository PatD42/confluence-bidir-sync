# Architecture - Constraints

---

## Technical Constraints

| Constraint | Description | Impact |
|------------|-------------|--------|
| **Python 3.9+** | Minimum Python version for broad compatibility | Use compatible type hints and syntax |
| **Confluence Cloud Only** | REST API v2; Data Center not supported | Simplifies API handling, single auth method |
| **Pandoc External Dependency** | Pandoc CLI must be installed separately | Requires user setup; subprocess invocation |
| **OSS Dependencies Only** | All dependencies must be open source | Limits library choices but ensures accessibility |

## Organizational Constraints

| Constraint | Description | Impact |
|------------|-------------|--------|
| **Solo/Small Team** | No formal process, agile/ad-hoc development | Documentation must be self-explanatory |
| **Git Clone Distribution** | Not published to PyPI; users clone repo | Installation via `pip install -e .` or requirements |
| **No CI/CD Initially** | Local testing; future GitHub Actions | Manual test runs; documented test commands |

## Conventions

### Coding Standards

- **Type hints required**: All public APIs must have complete type annotations
- **Docstrings required**: Google-style docstrings on all public functions and classes
- **Linting**: All code must pass `ruff` linting without errors
- **Type checking**: All code must pass `mypy` strict mode
- **No shell=True**: Never use `shell=True` in subprocess calls (security)

### Documentation Standards

- **Arc42 structure**: Architecture docs follow Arc42 methodology
- **ADR format**: Architectural decisions documented with context, options, consequences
- **Epic documentation**: Each epic has details, acceptance criteria, architecture, test strategy

### Testing Standards

- **Coverage threshold**: Maintain ≥80% code coverage (target: 90%)
- **Test structure**:
  - `tests/unit/` - Fast, isolated, mocked dependencies
  - `tests/e2e/` - Real Confluence integration (CONFSYNCTEST space)
  - `tests/integration/` - Real Pandoc, mocked Confluence (planned)
- **Contract tests**: Validate against Confluence API contract (planned)
- **Test naming**: `test_<function>_<scenario>_<expected>`

### Process Standards

- **Commit messages**: Conventional commits format (`feat:`, `fix:`, `docs:`, etc.)
- **Branch naming**: `epic-NNN/<short-description>` or `fix/<issue>`
- **Code review**: Self-review checklist before merge (solo project)

---
