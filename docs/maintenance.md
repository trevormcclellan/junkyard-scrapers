# Dependency maintenance for the combined repository

The supplied [dependency update policy](dependency-update-policy.md) is the source
of the schedule. All routine updates use native Dependabot `quarterly` intervals:

| Ecosystem | Directory | Covered files |
| --- | --- | --- |
| pip | `/` | `requirements.txt`, `requirements-build.txt`, `pyproject.toml` |
| docker | `/` | Both targets in `Dockerfile` |
| github-actions | `/` | `.github/workflows/ci.yml` |

Minor and patch version updates are grouped by ecosystem. Major versions get
separate PRs; they are not suppressed. Groups apply only to **version updates**,
so routine grouping does not defer security updates. No npm or docker-compose
entry is added because neither ecosystem has a manifest here. Apply the policy
separately to the repository that actually owns production Compose files.
See [GitHub's schedule and grouping reference](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference).

## GitHub settings still require verification

A committed Dependabot file cannot enable repository security features. In
[junkyard-scrapers security settings](https://github.com/trevormcclellan/junkyard-scrapers/settings/security_analysis),
enable/verify Dependency Graph, Dependabot alerts and Dependabot security updates.
These account-level settings were not changed or verified in the restricted local
environment. Keep them enabled on the old frontend repository while its old image
is still deployed; archive/retire it after the combined deployment is verified.
Require the CI check and human review before merge; do not enable auto-merge or
automatic deployment.

Security response is continuous: review critical applicable vulnerabilities as
soon as practical (target 24–48 hours), high severity within 7 days, and medium/low
at the next quarterly window unless exposure warrants earlier action.

## Lock and runtime updates

`requirements.txt` is the committed runtime lock: it pins direct **and transitive**
packages and is also the package's dependency source, avoiding a second list of
versions in `pyproject.toml`. `requirements-build.txt` pins the packaging toolchain.
No platform-specific freeze of the developer's machine is used. Both Docker
images consume these same files. CI installs the pins with dependency resolution
and runs `pip check`; `scripts/check_lock.py` also rejects missing transitive pins.
Incompatible or incomplete locks fail the PR.

For each quarterly window, review pending PRs and upstream release notes. When a
new dependency version adds/removes transitive requirements, update the complete
lock in a clean Python 3.14 environment, inspect the diff, run the test suite and
build both images. Pin any newly introduced transitive dependency; do not merge
an update that silently leaves new dependencies unconstrained. Major upgrades
need an individual compatibility review. Docker rebuilds alone do not change
pinned Python packages.

The initial upgrade uses these published releases, checked on 2026-11-09:

| Component | Previous | New |
| --- | --- | --- |
| Python image | 3.9-slim | 3.14.10-slim-bookworm |
| Beautiful Soup | 4.12.2 | 4.15.0 |
| Requests | 2.31.0 | 2.34.2 |
| PyMongo | 4.7.3 | 4.19.0 |
| python-dotenv | 1.0.1 | 1.2.4 |
| Flask | 3.0.3 | 3.1.3 |
| Gunicorn | 22.0.0 | 26.2.0 |

Versions are pinned to releases found in the [PyPI package index](https://pypi.org/).
The [official Python image manifest](https://github.com/docker-library/official-images/blob/master/library/python)
includes the selected Python tag. Gunicorn's
[release notes](https://gunicorn.org/news/) describe stricter HTTP parsing and
removal of the Eventlet worker; this app uses the standard WSGI worker and no
Eventlet configuration. Test the actual reverse proxy during rollout. Gunicorn's
news page mentions newer ASGI fixes, but 26.2.0 was the published PyPI version
available to verification; no unpublished version was pinned.
[PyMongo's compatibility requirements](https://pypi.org/project/pymongo/4.19.0/)
require checking the deployed MongoDB server before rollout.

Local verification used the host Python 3.10 and preinstalled libraries for source
regression tests. Package downloads were blocked by DNS/network restrictions;
Docker's snap launcher failed in the sandbox. Installation of the new lock,
Python 3.14 execution, container builds and live upstream/database smoke tests
therefore remain CI/staging checks, not locally proven results.
