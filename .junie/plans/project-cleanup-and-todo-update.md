---
sessionId: session-260808-155216-id54
---

# Implementation Status: ✓ Done (all 4 Delivery Steps completed)

# Requirements

### Overview & Goals
Audit the current state of aquaPI (checking which `ToDo` items are actually already implemented), remove legacy/stale artifacts that no longer belong in the repository, and rewrite `ToDo` so it reflects reality.

### Scope
**In Scope**
- Review `ToDo` line by line against the current codebase and move/rewrite entries that are already implemented into the `DONE` section (or delete them if superseded).
- Identify and remove stale, no-longer-needed local artifacts from the working tree (e.g. leftover debug logs, obsolete pickle/backup files) and from what's tracked in git going forward.
- Fix the broken `.gitignore` pattern for the QuestDB tarballs and stop tracking those large binaries going forward.
- Produce an updated `ToDo` file as the single source of truth for outstanding work.

**Out of Scope**
- Rewriting git history to purge already-committed large blobs (`questdb-*.tar.gz`, `quest_home.tar.gz`) - this is destructive to a shared repo and must be a separate, explicitly-approved action.
- Implementing any of the still-open `ToDo` features themselves (macros, Telegram bot, packaging, etc.) - this task is about status review and cleanup only.
- Any change to `AGENTS.md` (already handled in previous tasks).

### Functional Requirements
- `ToDo` accurately separates **open** items from **DONE** items, based on actual code inspection (not assumptions).
- Stale working-tree files that are clearly runtime/debug leftovers (not test fixtures, not needed for operation) are removed or flagged for removal.
- `.gitignore` is corrected so newly-generated QuestDB installation archives are properly ignored again.
- The user is informed about the large tracked binaries in git history as a known issue, with a recommendation (not an automatic action) on how to address it later.

### Non-Functional Requirements
- No behavioral/runtime code changes - this is a documentation and repo-hygiene task, `pytest -m "not questdb"` must still pass unchanged.

# Technical Design

### Current Implementation (findings from investigation)
- `ToDo` (205 lines) mixes long-outstanding open items with a `DONE` section; several "open" items are actually already implemented:
  - Three-tier auth (`viewer`/`operator`/`admin`) is fully implemented in `aquaPi/auth.py` (`roles_required()`, `User.role`), while `ToDo` line 62-64 still lists "user authentication ... three access levels" as open.
  - `logging.WARNING`-as-BRIEF abuse (line 5) still exists exactly as described in `aquaPi/__init__.py` (`log.brief = log.warning`, `addLevelName(WARN, 'LOG')`) - genuinely still open.
  - "remove all Jinja templating in favor of Vuetify" (line 42) is **mostly** done (git log shows `Remove legacy Jinja pages and dead static assets`); only `login.html.jinja2`, `reset_password_request.html.jinja2`, `reset_password_confirm.html.jinja2` remain (auth pages, pre-SPA-login) - needs a note reflecting the reduced scope, not a full removal.
  - "REST API: some endpoints return text, others json, should be all json" (line 69): `aquaPi/api.py` already consistently uses `Response(..., mimetype='application/json')` / `jsonify` across all checked endpoints - appears done.
  - "use package gettext for backend i18n" (line 67): no `gettext`/`babel` usage found anywhere in `aquaPi/*.py` - still open.
  - "add 'click' cmdline options" (line 65): no `click` usage found - still open.
- Working tree contains clear runtime/debug leftovers that are not part of the source: `run.log` (root, ignored via `*.log` but physically present), `instance/*.bak`, and `instance/nodes.pickle`/`nodes.pickle.bak` alongside the now-used `*.sqlite` files (superseded by DB-backed config per `ToDo` DONE entry "config persistance ... machineroom config is pickled, user prefs are in browser store" vs. actual `.sqlite` files present) - needs to be verified against `db.py`/`machineroom` to confirm which of `nodes.pickle`/`nodes.sqlite`/`topo.sqlite` are still actually read at runtime before deleting anything.
- `.gitignore` line `!questdb-*-.tar.gz` is a no-op typo (extra dash before `.tar.gz` means it matches nothing) - the intended un-ignore for release tarballs never applied, and both `questdb-7.1.3-no-jre-bin.tar.gz` (7.4 MB) and `questdb-7.1.3-rt-linux-amd64.tar.gz` (29 MB) are actually tracked in git, making the repo unnecessarily heavy (`git rev-list` shows these as the two largest blobs, plus a stray `quest_home.tar.gz` blob from history, ~1.8 MB, that is no longer present in the working tree).
- `questdb-7.1.3/` (extracted install, 45 MB) is correctly gitignored and untracked already - no action needed there beyond confirming it stays out of git.

### Key Decisions
- **Do not rewrite git history** in this pass (`git filter-repo`/BFG to purge the tarball blobs) - only stop tracking the files going forward (`git rm --cached`) and fix `.gitignore`, since history rewriting affects all collaborators/branches and needs explicit, separate sign-off.
- **Verify before deleting** any `instance/*.pickle*` file by checking `aquaPi/machineroom/__init__.py`/`db.py` for which files are actually loaded at startup, so nothing currently in use is removed.
- Rewrite `ToDo` in place (keep its existing two-section `open` / `DONE` structure and terse bullet style) rather than introducing a new format, to stay consistent with the project's existing convention.

### Proposed Changes
1. Cross-check every open `ToDo` entry against the current code (`auth.py`, `api.py`, `machineroom/`, templates) and reclassify.
2. Update `.gitignore`'s QuestDB tarball pattern.
3. `git rm --cached` the two large tracked tarballs (they stay on disk, just untracked) and confirm they're now covered by `.gitignore`.
4. Identify and remove clearly-obsolete local files (`run.log`, confirmed-unused `instance/*.bak`/`*.pickle.bak`) after verifying they're not read by the app.
5. Rewrite `ToDo` with the corrected open/DONE split and a short new note about the git-history bloat (as a recommendation, not an action taken).

### File Structure
- Modified: `ToDo`, `.gitignore`.
- Removed from git tracking (kept on disk or deleted if confirmed stale): `questdb-7.1.3-no-jre-bin.tar.gz`, `questdb-7.1.3-rt-linux-amd64.tar.gz`, `run.log`, obsolete `instance/*.bak` files.

### Risks
- Misclassifying a `ToDo` item as "done" without full verification could hide real remaining work - mitigated by grepping/reading the actual implementing code for each reclassified item before moving it.
- Deleting an `instance/*.pickle*` file that's still read as a fallback could break local dev state - mitigated by checking the loading code first and preferring `git rm --cached`/`.gitignore` fixes (non-destructive) over outright deletion where uncertain.

# Testing

### Validation Approach
- Run `pytest -m "not questdb"` after the changes to confirm no runtime code was touched and the suite still passes.
- After `git rm --cached` on the tarballs, run `git status` to confirm they show as untracked (not deleted) and are now caught by `.gitignore`.

### Edge Cases
- Confirm `flask run` / `./run` still starts cleanly after any `instance/` file cleanup (no missing pickle causing a crash instead of a graceful re-create).

# Delivery Steps

### ✓ Step 1: Audit ToDo items against current code and reclassify
`ToDo` accurately reflects which listed features are implemented and which remain open.
- Check auth roles (`viewer`/`operator`/`admin`) in `aquaPi/auth.py` and move the "three access levels" item to DONE.
- Check `aquaPi/api.py` response formats and move the "REST API should be all JSON" item to DONE if confirmed.
- Check remaining Jinja templates under `aquaPi/templates/` and rewrite the "remove all Jinja templating" item to reflect that only the pre-login auth pages remain.
- Confirm `gettext`/`babel` and `click` are still absent from `aquaPi/*.py`, keep those items open.
- Verify which `instance/*.pickle*` / `*.sqlite` files are actually loaded by `machineroom`/`db.py` at startup, to inform later cleanup decisions.

### ✓ Step 2: Fix .gitignore and stop tracking large QuestDB tarballs
The two QuestDB release tarballs are no longer tracked by git and are properly ignored going forward.
- Correct the broken `!questdb-*-.tar.gz` pattern in `.gitignore`.
- Run `git rm --cached` on `questdb-7.1.3-no-jre-bin.tar.gz` and `questdb-7.1.3-rt-linux-amd64.tar.gz`, keeping the files on disk.
- Confirm via `git status`/`git check-ignore` that both files are now untracked and ignored.
- Document in the plan output that purging these blobs from git *history* is a separate, explicitly-approved follow-up (not done here).

### ✓ Step 3: Clean up confirmed-stale local artifacts
Runtime/debug leftovers that are not needed by the running app or tests are removed from the working tree.
- Remove root-level `run.log` (leftover debug output, already `.gitignore`d).
- Remove `instance/*.bak`/`nodes.pickle.bak`-style files confirmed in stage 1 to be unused by current startup code.
- Leave any file whose usage could not be fully confirmed untouched, and note it instead.

### ✓ Step 4: Rewrite ToDo with updated status and run verification
`ToDo` is committed to the working tree in its final, updated form and the test suite still passes.
- Apply all reclassifications from stage 1 to `ToDo`, keeping its existing open/DONE structure and bullet style.
- Add a short note under open items about the git-history bloat from the QuestDB tarballs, recommending a future history rewrite.
- Run `pytest -m "not questdb"` to confirm no regressions from the cleanup.