# Releasing

`pyweft` and `pyweft-ui` are released to PyPI separately, each with its own
version, by pushing a tag. GitHub runs the tests, builds the package and
publishes it (`.github/workflows/publish.yml`); nothing is uploaded by hand
and no password or token is stored anywhere.

## A release

1. **Choose the new version.** Below 1.0: a new feature, or anything that
   changes how existing apps behave, raises the middle number
   (`0.2.0` → `0.3.0`); bug fixes only raise the last (`0.2.0` → `0.2.1`).
2. **Set it** in the package's `__init__.py`, the one place it lives:
   - `pyweft`: `src/pyweft/__init__.py`
   - `pyweft-ui`: `packages/pyweft-ui/src/pyweft_ui/__init__.py`
3. **Update the changelog** (`CHANGELOG.md` or
   `packages/pyweft-ui/CHANGELOG.md`): rename **Unreleased** to the new
   version and start a fresh, empty **Unreleased** above it.
4. **Releasing `pyweft-ui` for a new `pyweft`?** Release `pyweft` first,
   then raise the range in `packages/pyweft-ui/pyproject.toml`
   (`pyweft>=0.3,<0.4`).
5. **Commit and push to `main`**, then tag that commit and push the tag:

   ```bash
   git tag v0.3.0                 # pyweft
   git push origin v0.3.0

   git tag pyweft-ui-v0.2.0       # pyweft-ui
   git push origin pyweft-ui-v0.2.0
   ```

6. **Watch it** on the repository's Actions tab. If the tests fail, or the
   tag doesn't match the version in `__init__.py`, nothing is published:
   fix it, delete the tag (`git push origin :v0.3.0`, `git tag -d v0.3.0`)
   and tag again.

A minute or two later the release is on PyPI, and `uv add -U pyweft`
picks it up.

**A published version can never be replaced or reused.** If a release is
broken, release a fix as the next version; on pypi.org you can also "yank"
the broken one so new installs skip it.

## A practice run on TestPyPI

On GitHub, **Actions → Publish → Run workflow**, choose the package, and it
is built and uploaded to <https://test.pypi.org> instead. Try it with:

```bash
uv pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ pyweft
```

TestPyPI also keeps every version forever, so a second practice run of the
same version is skipped; raise the version (`0.2.0` → `0.2.1.dev1`) to
practise again.

## One-time setup

Done once, by the owner of the PyPI accounts:

1. **Accounts** on <https://pypi.org> and <https://test.pypi.org>, each with
   two-factor authentication on.
2. **Trusted publishers.** On <https://pypi.org/manage/account/publishing/>,
   under *Add a new pending publisher*, add one entry per package:

   | Field | `pyweft` | `pyweft-ui` |
   |---|---|---|
   | PyPI Project Name | `pyweft` | `pyweft-ui` |
   | Owner | `prassanthn` | `prassanthn` |
   | Repository name | `PyWeft` | `PyWeft` |
   | Workflow name | `publish.yml` | `publish.yml` |
   | Environment name | `pypi` | `pypi` |

   Then the same two on <https://test.pypi.org/manage/account/publishing/>,
   with the environment name `testpypi`.
3. **Optionally, a safety catch:** on GitHub, **Settings → Environments →
   pypi → Required reviewers**, add yourself. Every release then waits for
   your click on the Actions tab before it uploads.

The first tag pushed for each package creates the project on PyPI, owned by
the account that added the pending publisher.

## After the first release

Change the install instructions in `README.md`,
`docs/getting-started.md` and `packages/pyweft-ui/README.md` from the
GitHub URLs to `uv add pyweft` and `uv add pyweft-ui`.
