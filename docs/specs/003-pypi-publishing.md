# Spec 003: PyPI Publishing Plan

**Status**: Draft
**Created**: 2026-02-05
**Target Version**: 0.1.0

---

## Overview

This specification outlines the plan for publishing KameleonDB to PyPI, including pre-publishing fixes, CI/CD workflow setup, and release process documentation.

## Current State Assessment

### What's Ready

| Item | Status | Notes |
|------|--------|-------|
| pyproject.toml | ✅ | Modern hatchling build, well-structured |
| Build backend | ✅ | Using hatchling (best practice) |
| src-layout | ✅ | Standard Python packaging layout |
| License | ✅ | Apache-2.0 with LICENSE file |
| README | ✅ | Comprehensive documentation |
| Keywords | ✅ | Good discoverability terms |
| Classifiers | ✅ | Appropriate for Alpha release |
| Entry points | ✅ | `kameleondb-mcp` CLI configured |
| Optional deps | ✅ | mcp, dev, docs groups defined |
| Type hints | ✅ | py.typed marker, mypy strict |
| Tests | ✅ | Unit + integration tests exist |
| CI | ✅ | Linting, testing on 3.11-3.13 |

### Issues to Resolve

| Issue | Priority | Description |
|-------|----------|-------------|
| Version mismatch | 🔴 Critical | pyproject.toml=`0.1.0`, __init__.py=`0.2.0-alpha` |
| Changelog empty | 🔴 Critical | Only template content, needs release notes |
| No publish workflow | 🔴 Critical | No GitHub Actions for PyPI |
| PostgreSQL required | 🟡 Medium | psycopg in core deps, but SQLite supported |
| Author email missing | 🟡 Medium | No contact email in metadata |
| No MANIFEST.in | 🟢 Low | Hatchling handles this, but explicit is safer |

---

## Phase 1: Pre-Publishing Fixes

### 1.1 Version Synchronization

**Decision**: Use single source of truth with dynamic versioning.

**Option A: Static version in pyproject.toml (Recommended for simplicity)**
```toml
# pyproject.toml
version = "0.1.0"
```
```python
# src/kameleondb/__init__.py
from importlib.metadata import version
__version__ = version("kameleondb")
```

**Option B: Dynamic version from __init__.py**
```toml
# pyproject.toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/kameleondb/__init__.py"
```

**Recommendation**: Option A - keeps version in pyproject.toml as the source of truth, which is standard for modern Python packaging.

### 1.2 Dependency Restructuring

Make PostgreSQL optional to reduce install footprint for SQLite-only users:

```toml
[project]
dependencies = [
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
postgresql = [
    "psycopg[binary]>=3.1",
]
sqlite = []  # No extra deps needed, included in Python stdlib
mcp = [
    "mcp[cli]>=1.2.0",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
    "pre-commit>=3.0",
]
docs = [
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.24",
]
all = [
    "kameleondb[postgresql,mcp,dev,docs]",
]
```

**Impact**:
- `pip install kameleondb` - Core only (SQLite works out of box)
- `pip install kameleondb[postgresql]` - With PostgreSQL support
- Update README installation instructions
- Update CI to use `kameleondb[postgresql,dev]`

### 1.3 Author Metadata

Add contact email for PyPI:

```toml
authors = [
    { name = "KameleonDB Contributors", email = "kameleondb@example.com" }
]
maintainers = [
    { name = "Marcos Natã", email = "marcos@example.com" }
]
```

### 1.4 Changelog Population

Update CHANGELOG.md with actual release notes:

```markdown
# Changelog

## [Unreleased]

## [0.1.0] - 2026-02-XX

### Added
- Initial public release
- Core KameleonDB engine with dynamic schema management
- PostgreSQL backend with JSONB storage
- SQLite backend with JSON1 extension
- Entity and field management APIs
- Relationship support (one-to-one, one-to-many, many-to-one)
- Schema context builder for LLM SQL generation
- Query validation with injection protection
- MCP (Model Context Protocol) integration
- Tool registry for agent frameworks (OpenAI, Anthropic)
- Comprehensive type hints and py.typed marker

### Architecture
- Meta-tables for schema storage (`kdb_entity_definitions`, `kdb_field_definitions`)
- Single data table (`kdb_records`) with JSON column
- Schema-on-reason: no migrations needed for field changes
```

---

## Phase 2: GitHub Actions Publish Workflow

### 2.1 Workflow File

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      target:
        description: 'Target PyPI (testpypi or pypi)'
        required: true
        default: 'testpypi'
        type: choice
        options:
          - testpypi
          - pypi

jobs:
  build:
    name: Build distribution
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build dependencies
        run: python -m pip install --upgrade pip build

      - name: Build package
        run: python -m build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  test-install:
    name: Test installation
    needs: build
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - name: Install wheel
        run: pip install dist/*.whl

      - name: Test import
        run: python -c "from kameleondb import KameleonDB; print('Import successful')"

      - name: Test version
        run: python -c "import kameleondb; print(f'Version: {kameleondb.__version__}')"

  publish-testpypi:
    name: Publish to TestPyPI
    needs: test-install
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch' && github.event.inputs.target == 'testpypi'
    environment:
      name: testpypi
      url: https://test.pypi.org/p/kameleondb
    permissions:
      id-token: write
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/

  publish-pypi:
    name: Publish to PyPI
    needs: test-install
    runs-on: ubuntu-latest
    if: github.event_name == 'release' || (github.event_name == 'workflow_dispatch' && github.event.inputs.target == 'pypi')
    environment:
      name: pypi
      url: https://pypi.org/p/kameleondb
    permissions:
      id-token: write  # Trusted publishing
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

### 2.2 PyPI Trusted Publishing Setup

1. Go to https://pypi.org/manage/account/publishing/
2. Add new pending publisher:
   - PyPI Project Name: `kameleondb`
   - Owner: `marcosnataqs`
   - Repository name: `kameleondb`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

3. Repeat for TestPyPI at https://test.pypi.org/manage/account/publishing/
   - Environment name: `testpypi`

### 2.3 GitHub Environment Setup

Create two environments in GitHub repository settings:

1. **testpypi**
   - No protection rules (for testing)

2. **pypi**
   - Required reviewers (optional, for safety)
   - Restrict to `main` branch only

---

## Phase 3: Release Process

### 3.1 Version Bump Checklist

Before each release:

1. [ ] Update version in `pyproject.toml`
2. [ ] Update `CHANGELOG.md` with release notes
3. [ ] Run full test suite: `pytest tests/`
4. [ ] Run linting: `ruff check src tests && ruff format --check src tests`
5. [ ] Run type checking: `mypy src/kameleondb`
6. [ ] Build locally: `python -m build`
7. [ ] Test local wheel: `pip install dist/*.whl`

### 3.2 Release Steps

1. **Create release branch** (optional for major releases):
   ```bash
   git checkout -b release/v0.1.0
   ```

2. **Validate on TestPyPI**:
   - Trigger workflow manually with `testpypi` target
   - Test installation: `pip install -i https://test.pypi.org/simple/ kameleondb`

3. **Create GitHub Release**:
   - Tag: `v0.1.0`
   - Title: `v0.1.0 - Initial Release`
   - Body: Copy from CHANGELOG.md
   - Publish release → triggers PyPI publish

4. **Verify PyPI**:
   - Check https://pypi.org/project/kameleondb/
   - Test: `pip install kameleondb`

### 3.3 Versioning Strategy

Follow [Semantic Versioning](https://semver.org/):

- **0.x.y**: Pre-1.0 development (breaking changes allowed in minor versions)
- **MAJOR.MINOR.PATCH** after 1.0:
  - MAJOR: Breaking API changes
  - MINOR: New features, backward compatible
  - PATCH: Bug fixes only

Suggested version progression:
- `0.1.0` - Initial PyPI release
- `0.2.0` - Query Intelligence features
- `0.3.0` - Hybrid Storage Phase 2
- `1.0.0` - Production ready, stable API

---

## Phase 4: Post-Publishing Tasks

### 4.1 Documentation Updates

- [ ] Update README badges (once published, PyPI badge will work)
- [ ] Add installation section with all optional dependencies
- [ ] Create GitHub Pages documentation site

### 4.2 Monitoring

- [ ] Set up PyPI download statistics tracking
- [ ] Configure Dependabot for dependency updates
- [ ] Add security policy (SECURITY.md)

### 4.3 Community

- [ ] Add CONTRIBUTING.md guidelines
- [ ] Create issue templates
- [ ] Add CODE_OF_CONDUCT.md

---

## Implementation Checklist

### Must Have (for 0.1.0 release)

- [ ] Fix version mismatch (sync to 0.1.0)
- [ ] Populate CHANGELOG.md
- [ ] Create publish.yml workflow
- [ ] Set up PyPI trusted publishing
- [ ] Create GitHub environments
- [ ] Test on TestPyPI
- [ ] Create v0.1.0 release

### Should Have

- [ ] Make PostgreSQL optional dependency
- [ ] Add author email
- [ ] Update CI to use optional deps syntax
- [ ] Add MANIFEST.in for explicit includes

### Nice to Have

- [ ] Automatic version bumping script
- [ ] Release notes generation from commits
- [ ] Changelog generation tooling

---

## Appendix: Local Build Testing

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Check the built package
twine check dist/*

# Test install locally
pip install dist/kameleondb-0.1.0-py3-none-any.whl

# Verify
python -c "from kameleondb import KameleonDB; print('OK')"
```

## Appendix: TestPyPI Manual Upload

For manual testing before workflow is ready:

```bash
# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ kameleondb
```
