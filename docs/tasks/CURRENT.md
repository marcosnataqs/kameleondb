# Current Tasks

Active work in progress.

---

## In Progress

### CLI Tool Implementation

Add a command-line interface using Typer. See [spec](../specs/004-cli-tool.md).

**Phase 1: Core Structure**
- [ ] Add `typer` and `rich` to dependencies
- [ ] Create CLI module structure (`src/kameleondb/cli/`)
- [ ] Add `kameleondb` entry point to pyproject.toml
- [ ] Implement global options (--database, --json, --echo)

**Phase 2: Schema Commands**
- [ ] `schema list`
- [ ] `schema describe`
- [ ] `schema create`
- [ ] `schema drop`
- [ ] `schema add-field`
- [ ] `schema context`

**Phase 3: Data Commands**
- [ ] `data insert`
- [ ] `data get`
- [ ] `data update`
- [ ] `data delete`
- [ ] `data list`

**Phase 4: Query & Storage Commands**
- [ ] `query run`
- [ ] `query validate`
- [ ] `storage status`
- [ ] `storage materialize`
- [ ] `storage dematerialize`

**Phase 5: Admin Commands**
- [ ] `init`
- [ ] `info`
- [ ] `changelog`

**Phase 6: Polish**
- [ ] Rich table output
- [ ] Progress bars
- [ ] Error handling
- [ ] Tests

---

## Blocked

### PyPI Publishing

Waiting on CLI implementation to complete before v0.1.0 release.

- [x] Fix version mismatch
- [x] Populate CHANGELOG.md
- [x] Create publish.yml workflow
- [ ] **Blocked**: Complete CLI first
- [ ] Set up PyPI trusted publishing
- [ ] Test on TestPyPI
- [ ] Create v0.1.0 release

---

## Up Next

_Pull from [BACKLOG.md](./BACKLOG.md)_
