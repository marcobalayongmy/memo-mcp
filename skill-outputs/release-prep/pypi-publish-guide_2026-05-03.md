# PyPI Publish Guide — memo-mcp v0.1.0

First-time PyPI publisher guide. Follow in order: TestPyPI dry-run first, then real PyPI.

---

## Prerequisites

Before you start, make sure:

- Your code is committed and pushed to GitHub (the repository must be public or have GitHub Actions enabled)
- You have run `pytest` locally and all tests pass
- You know your GitHub repository URL (e.g. `https://github.com/YOUR_USERNAME/memo-mcp`)

---

## Part 1 — Create accounts

### 1a. Create a PyPI account (real PyPI)

1. Go to https://pypi.org/account/register/
2. Fill in username, email, and password. Choose a username you're happy with — it's public.
3. Verify your email address (check your inbox for the confirmation link).
4. **Enable 2FA** — PyPI now requires it for publishing.
   - Go to Account Settings → Two-factor authentication
   - Use an authenticator app (Google Authenticator, Authy, 1Password, etc.)
   - Save your recovery codes somewhere safe.

### 1b. Create a TestPyPI account (dry-run target)

TestPyPI is a separate sandbox — it has its own accounts, separate from pypi.org.

1. Go to https://test.pypi.org/account/register/
2. Use the **same username** as your PyPI account (you can, and it keeps things simple).
3. Verify your email and enable 2FA here too.

---

## Part 2 — Create the GitHub Actions environment

GitHub "environments" are deployment targets that can have protection rules and are required for OIDC trusted publishing.

1. Open your GitHub repository in a browser.
2. Click **Settings** (top tab bar).
3. In the left sidebar, click **Environments**.
4. Click **New environment**.
5. Name it exactly: `publish` (must match the `environment: publish` in `publish.yml`).
6. Click **Configure environment**.
7. You can leave all protection rules empty for now (no required reviewers needed for a personal project).
8. Click **Save protection rules**.

---

## Part 3 — Register a trusted publisher on TestPyPI

Trusted publishing means PyPI grants publish rights to a specific GitHub Actions workflow — no API tokens needed.

1. Go to https://test.pypi.org and log in.
2. Since `memo-mcp` does not exist on TestPyPI yet, you need to register a **pending** trusted publisher (for a package you haven't published yet):
   - Click your username (top right) → **Your projects**
   - Scroll to the bottom: look for **"Publishing"** or go directly to https://test.pypi.org/manage/account/publishing/
3. Fill in the **"Add a new pending publisher"** form:
   - **PyPI Project Name:** `memo-mcp`
   - **Owner:** your GitHub username (e.g. `marcobalayong`)
   - **Repository name:** `memo-mcp`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `publish`
4. Click **Add**.

You should see `memo-mcp` appear in your pending publishers list.

---

## Part 4 — Register a trusted publisher on real PyPI

Same steps, different site.

1. Go to https://pypi.org and log in.
2. Go to https://pypi.org/manage/account/publishing/
3. Fill in the **"Add a new pending publisher"** form:
   - **PyPI Project Name:** `memo-mcp`
   - **Owner:** your GitHub username
   - **Repository name:** `memo-mcp`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `publish`
4. Click **Add**.

---

## Part 5 — TestPyPI dry-run (v0.0.1a0)

Before touching real PyPI, prove the whole pipeline works with a pre-release version.

### 5a. Update the version to 0.0.1a0

Open `pyproject.toml` and change the version line:

```toml
version = "0.0.1a0"
```

Also update `src/memo_mcp/__init__.py`:

```python
__version__ = "0.0.1a0"
```

### 5b. Commit and push

```powershell
git add pyproject.toml src/memo_mcp/__init__.py
git commit -m "chore: bump version to 0.0.1a0 for TestPyPI dry-run"
git push
```

### 5c. Push the tag

Tags trigger the publish workflow (`on: push: tags: "v*"`):

```powershell
git tag v0.0.1a0
git push origin v0.0.1a0
```

### 5d. Watch the GitHub Actions run

1. Go to your GitHub repository.
2. Click the **Actions** tab.
3. You should see a workflow run named "Publish to PyPI" triggered by the tag push.
4. Watch it: `test` job runs first (pytest), then `publish` job runs if tests pass.
5. The `publish` job will publish to **TestPyPI** — wait, but `publish.yml` currently publishes to real PyPI, not TestPyPI.

**Important:** The current `publish.yml` always publishes to PyPI. For the dry-run, you have two options:

**Option A (simplest):** Edit `publish.yml` temporarily to publish to TestPyPI for the `0.0.1a0` tag, then revert. Add `repository-url`:

```yaml
- name: Publish to TestPyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    repository-url: https://test.pypi.org/legacy/
```

**Option B (no workflow change):** Skip the TestPyPI dry-run and go straight to v0.1.0 on real PyPI. Riskier but simpler. Only do this if you're confident everything is correct.

If you go with Option A, after the dry-run succeeds, revert `publish.yml` to the original (no `repository-url` line), then proceed to Part 6.

### 5e. Verify the TestPyPI install

After the workflow succeeds:

```powershell
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ memo-mcp==0.0.1a0
memo-mcp --help
memo-mcp serve --help
```

The `--extra-index-url https://pypi.org/simple/` is needed because TestPyPI doesn't host memo-mcp's dependencies (mcp, typer, etc.) — they come from real PyPI.

Expected output from `memo-mcp --help`:
```
Usage: memo-mcp [OPTIONS] COMMAND [ARGS]...
...
Commands:
  reindex  Rebuild the FTS5 search index.
  serve    Start the MCP server on stdio.
```

If that works, the package is correctly built and installable. 

---

## Part 6 — Cut the real v0.1.0 release

### 6a. Reset version to 0.1.0

```toml
# pyproject.toml
version = "0.1.0"
```

```python
# src/memo_mcp/__init__.py
__version__ = "0.1.0"
```

### 6b. Revert publish.yml (if you changed it in Part 5)

Make sure `publish.yml` does NOT have `repository-url` — it should publish to real PyPI.

### 6c. Commit, push, and tag

```powershell
git add pyproject.toml src/memo_mcp/__init__.py
git commit -m "chore: bump version to 0.1.0"
git push
git tag v0.1.0
git push origin v0.1.0
```

### 6d. Watch the Actions run

Go to the Actions tab again. The `test` → `publish` pipeline runs. The `publish` job now has an OIDC token (because it runs in the `publish` environment) and pushes to real PyPI.

### 6e. Verify the real PyPI install

After the run succeeds (usually 1–3 minutes):

```powershell
pip install memo-mcp
memo-mcp --help
```

Check the package page: https://pypi.org/project/memo-mcp/

---

## Part 7 — Add to Claude Desktop

Once installed, add to your Claude Desktop config:

**Windows path:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo-mcp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude Desktop. You should see `memo` in the MCP tools list (hammer icon).

Test by asking Claude: "Add a note: this is my first memo-mcp note" — it should call `notes.add`.

---

## Troubleshooting

### "403 Forbidden" during publish

- The trusted publisher registration didn't match. Double-check:
  - Workflow filename is exactly `publish.yml` (not `publish.yaml`)
  - Environment name is exactly `publish`
  - GitHub username and repo name are correct (case-sensitive)
- Wait a minute and retry — there can be a propagation delay.

### "Package already exists" error

- You're trying to publish a version that's already on PyPI. Bump the version and re-tag.
- PyPI does not allow re-uploading the same version, even if you delete the file.

### Tests fail in GitHub Actions but pass locally

- Check that you've pushed all local commits before pushing the tag.
- The workflow runs against what's on GitHub, not your local tree.

### `memo-mcp` not found after install

- It may not be on your PATH. Try `python -m memo_mcp` or use `uvx memo-mcp serve` instead.
- If you used a virtualenv, activate it first.

### OIDC error: "audience does not match"

- The GitHub environment name (`publish`) must match exactly what you entered in the trusted publisher form on PyPI.

---

## Quick reference — version locations

Two files to update when cutting a release:

| File | Line |
|------|------|
| `pyproject.toml` | `version = "0.1.0"` |
| `src/memo_mcp/__init__.py` | `__version__ = "0.1.0"` |

---

## Summary checklist

- [ ] PyPI account created + 2FA enabled
- [ ] TestPyPI account created + 2FA enabled
- [ ] GitHub environment `publish` created
- [ ] Trusted publisher registered on TestPyPI (pending publisher for `memo-mcp`)
- [ ] Trusted publisher registered on PyPI (pending publisher for `memo-mcp`)
- [ ] TestPyPI dry-run: push `v0.0.1a0` tag → Actions green → `pip install` works
- [ ] Revert any `publish.yml` changes from the dry-run
- [ ] v0.1.0: bump version, push `v0.1.0` tag → Actions green → `pip install memo-mcp` works
- [ ] Claude Desktop config updated + restart → tools visible
