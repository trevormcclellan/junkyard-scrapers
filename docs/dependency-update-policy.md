# Personal App Dependency Update Policy

## Purpose

Maintain personal applications deployed with Docker Compose (including Vue/Node.js, Flask/Python, and API services) while minimizing manual maintenance and avoiding untested production changes.

## Update Schedule

| Update category | Detection/check frequency | Review and deployment target | Notes |
| --- | --- | --- | --- |
| Critical security vulnerabilities | Continuous GitHub Dependabot alerts | As soon as practical, ideally within 24–48 hours | Prioritize internet-exposed services; assess exploitability, test, and deploy promptly. |
| High-severity security vulnerabilities | Continuous GitHub Dependabot alerts | Within 7 days when applicable/exploitable | Prioritize production dependencies and externally reachable applications. |
| Medium/low security vulnerabilities | Continuous GitHub Dependabot alerts | At next quarterly review, unless risk warrants sooner | Consider actual exposure and whether the affected code is reachable. |
| npm/Python dependency patch and minor versions | Quarterly | Quarterly maintenance window | Prefer grouped, reviewable pull requests. |
| npm/Python dependency major versions | Quarterly | Schedule individually as needed | Review migration notes and breaking changes; no obligation to upgrade immediately if supported and secure. |
| Dockerfile base images (Node, Python, etc.) | Quarterly, plus security alerts | Quarterly; sooner for applicable security issues | Rebuild application images after an approved change. |
| Docker Compose service image tags | Quarterly, plus security alerts where supported | Quarterly; sooner for applicable security issues | Use explicit versioned tags or digests where practical; review release notes and migrations. |
| Node.js/Python runtime versions | Quarterly | Before end of support; sooner for security concerns | Track runtime support separately from library versions. |
| GitHub Actions dependencies | Quarterly, plus security alerts | Quarterly; sooner for applicable security issues | Keep CI actions current. |
| Application health after deployment | Every deployment | Immediately after deployment | Verify service health, logs, and key functionality. |

**Cadence principle:** Routine updates can wait for the quarterly maintenance window. Security alerts must remain enabled and reviewed as they arrive; a quarterly version-update schedule is not a quarterly security-response schedule.

## GitHub Automation

1. Enable **Dependency Graph**, **Dependabot Alerts**, and **Dependabot Security Updates** for each applicable GitHub repository.
2. Add `.github/dependabot.yml` with a `quarterly` schedule for routine version updates. Configure the ecosystems actually present in each repository:
   - `npm` for Vue/Node.js `package.json` and lockfiles.
   - `pip` for Python dependency manifests.
   - `docker` for Dockerfile base-image references.
   - `docker-compose` for image references in Compose files.
   - `github-actions` for workflows, if present.
3. Use the actual manifest directories; do not assume all files are in the repository root. Group routine minor/patch updates where supported, and keep major updates separately reviewable.
4. Add GitHub Actions checks for dependency installation, builds, unit tests, and a small set of app-specific smoke tests. Keep lockfiles committed for reproducibility.
5. Dependabot and CI may open and test pull requests automatically, but **do not automatically merge or deploy updates**. Require human review and approval.

## Quarterly Maintenance Procedure

1. Review pending routine Dependabot pull requests and unaddressed security alerts.
2. Review release notes for major dependency versions, Docker base images, Compose services, and supported Node/Python runtimes.
3. Update one application (or one related group of dependencies) at a time.
4. Run automated build/tests; manually test login and data operations on the plant tracker, parser/database behavior on the junkyard checker, and representative API requests on the fuel optimizer.
5. Confirm current backups and a rollback path before database or other persistent-data migrations.
6. Merge approved changes, then deploy via the application's existing Docker Compose workflow.
7. Check `docker compose ps`, application logs, health checks, and critical user-facing functions; record the deployed version and any follow-up work.

## Deployment Rules

- **Locally built services (`build:`):** After approved source changes, update the checked-out repository, rebuild the service image (including a base-image pull when appropriate), and recreate the service using Docker Compose.
- **Prebuilt services (`image:`):** After approving a pinned image-tag or digest change, pull the new image and recreate the service using Docker Compose.
- Rebuilding a container does **not** automatically update pinned npm/Python dependencies; these require reviewed manifest/lockfile changes.
- `docker compose down` is generally unnecessary for a routine update. Preserve named volumes and avoid destructive cleanup.
- For stateful services such as MongoDB, verify backups, compatibility, and migration/rollback procedures before an upgrade.
- Do not use automatic container replacement (for example, Watchtower auto-updates) for these production applications.

## Instructions to Codex

Apply this policy incrementally to each repository. First inspect its dependency manifests, Dockerfile(s), Docker Compose file(s), existing CI, and deployment method. Propose the smallest repository-specific Dependabot and GitHub Actions configuration. Do not assume `build:` versus `image:` or a directory layout. Do not auto-merge, deploy, change production secrets, modify database contents, or perform destructive Docker operations. Validate configuration and tests locally where possible; present the changes for review before any production deployment.
