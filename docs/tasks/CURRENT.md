# Current Tasks

Active work in progress.

---

## In Progress

### PyPI Publishing Setup

Prepare and publish KameleonDB to PyPI. See [spec](../specs/003-pypi-publishing.md).

**Phase 1: Pre-Publishing Fixes**
- [ ] Fix version mismatch (pyproject.toml vs __init__.py)
- [ ] Populate CHANGELOG.md with release notes
- [ ] Make PostgreSQL an optional dependency
- [ ] Add author/maintainer email

**Phase 2: CI/CD Workflow**
- [ ] Create `.github/workflows/publish.yml`
- [ ] Set up PyPI trusted publishing
- [ ] Create GitHub environments (testpypi, pypi)

**Phase 3: Release**
- [ ] Test on TestPyPI
- [ ] Create v0.1.0 GitHub release
- [ ] Verify on PyPI

---

## Up Next

_Pull from [BACKLOG.md](./BACKLOG.md)_
