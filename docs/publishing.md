# Publishing

The package distribution name is `lfpolicy`; the import package is
`lfpolicy`; the primary CLI command is `lfpolicy`.

## Recommended PyPI Release Path

Use PyPI Trusted Publishing from GitHub Actions rather than storing a long-lived
PyPI token.

Configure a pending publisher in PyPI with:

- PyPI project name: `lfpolicy`
- Owner: `yongjip`
- Repository: `aws-datalake-guard`
- Workflow: `release.yml`
- Environment: `pypi`

Then publish by publishing a GitHub Release for a version tag such as `v0.10.0`,
or by manually dispatching the release workflow with `release_tag: v0.10.0`.
Pushing a tag alone does not publish to PyPI. The release workflow first
verifies that the tag matches the package version, builds the artifacts,
verifies distribution filenames and embedded metadata, checks them, smoke-tests
the built wheel through an installed `lfpolicy` CLI, uploads to PyPI through OIDC
when the version is not already published, then installs `lfpolicy` back from
PyPI and smoke-tests the published package.

```bash
git tag v0.10.0
git push origin v0.10.0
gh release create v0.10.0 --title "lfpolicy 0.10.0" --notes-file docs/release-notes/v0.10.0.md
```

Use the matching file under [`release-notes/`](release-notes/) as the GitHub
release body.

## Release Preflight

Before publishing, verify the release candidate from the repository root:

```bash
python -m unittest discover -s tests
python -m build
python -m twine check dist/*
python -m venv /tmp/lfpolicy-wheel-smoke
/tmp/lfpolicy-wheel-smoke/bin/python -m pip install --no-index --find-links dist lfpolicy
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy --version
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy generate examples/policy.py --output-file /tmp/lfpolicy-policy.json --force
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy generate examples/policy.py --output-file /tmp/lfpolicy-policy.json --check
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy check --desired /tmp/lfpolicy-policy.json --fail-on-findings
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy sample --output-dir /tmp/lfpolicy-demo
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy check \
  --desired /tmp/lfpolicy-demo/desired.json \
  --current-snapshot /tmp/lfpolicy-demo/current-snapshot.json \
  --fail-on-findings
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy review \
  --desired /tmp/lfpolicy-demo/desired.json \
  --current-snapshot /tmp/lfpolicy-demo/current-snapshot.json \
  --output-dir /tmp/lfpolicy-review-smoke \
  --force
/tmp/lfpolicy-wheel-smoke/bin/lfpolicy explain-batch \
  --requests examples/access-requests.json \
  --current-snapshot examples/access-current-snapshot.json \
  --output json \
  --output-file /tmp/lfpolicy-explain-batch.json
```

After the GitHub release workflow finishes, verify PyPI and the tag:

```bash
python -m pip index versions lfpolicy
git ls-remote --tags origin v0.10.0
```

The release workflow also runs this published-package smoke test automatically
after upload, or after skipping upload for a version already present on PyPI. It
installs the exact package version derived from the GitHub release tag, asserts
the CLI version, and retries briefly because a new project or version can take a
short time to become available through the package index.

## Manual Fallback

If Trusted Publishing is not configured yet, build locally and upload with a
project-scoped API token:

```bash
python -m pip install build twine
rm -rf dist build src/*.egg-info
python -m build
python -m twine check dist/*
TWINE_USERNAME=__token__ TWINE_PASSWORD="$PYPI_API_TOKEN" python -m twine upload dist/*
```
