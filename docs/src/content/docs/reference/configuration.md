---
title: Configuration
id: DOC-FC-REF-CONFIGURATION
type: Reference
status: Active
updated: "2026-10-09"
summary: The chart values an install sets on its deploy branch, and the environment the application reads.
---

An install configures the console through its deploy branch's chart values. The chart renders
most of them into the pods' environment; the second table names what the application reads.
Settings an operator edits in the console (agents, git identities, MCP doors) are runtime settings,
not configuration, and live in the [settings module](../../modules/settings/).

## Chart values

| Value | Sets |
| --- | --- |
| `githubOwner` | the GitHub owner the images are pulled from |
| `host` | the public hostname the Gateway routes to the console |
| `paused` | scales the console to zero |
| `images.app.tag` | the backend image's version |
| `images.web.tag` | the web tier's image version |
| `images.worker.tag` | the worker image every launched phase runs |
| `images.docs.tag` | the documentation site's image version |
| `imagePullSecrets` | the registry pull secret |
| `gateway.name` | the per-team Gateway the route attaches to |
| `gateway.namespace` | that Gateway's namespace |
| `persistence.size` | the archive volume holding receipts and run logs |
| `resources` | the backend container's requests and limits |
| `auth.proxySecret` | a Secret holding the web tier's proxy secret, when OIDC is off |
| `auth.proxySecretKey` | that Secret's key |
| `auth.existingSecret` | a Secret whose keys load into the backend's environment |
| `auth.teams.adminGroup` | the identity-provider group whose members are the console's admins; with OIDC on and a group named, every other signed-in user sees and acts on its teams' projects alone |
| `auth.oidc.enabled` | fronts the console with the sign-in proxy |
| `auth.oidc.issuer` | the app realm's OIDC issuer |
| `auth.oidc.clientId` | the realm's client |
| `auth.oidc.emailDomains` | the email domains the proxy admits |
| `auth.oidc.existingSecret` | the Secret holding the client and cookie secrets |
| `auth.oidc.image` | the sign-in proxy's image |
| `auth.execution.enabled` | publishes the execution door |
| `auth.execution.existingSecret` | the Secret holding the door's token |
| `auth.execution.tokenKey` | that Secret's key |
| `auth.execution.principal` | the machine caller's name, recorded as `execution#<name>` |
| `auth.execution.repositories` | the caller's repositories, `owner/name` or `owner/prefix*`, under the installation's owner |
| `events.enabled` | publishes the console's facts on the platform event bus |
| `events.servers` | the bus's in-cluster address |
| `events.seedSecret` | the bus grant's keypair Secret |
| `events.jwtSecret` | the bus grant's user JWT Secret |
| `config` | non-secret application environment, rendered into a ConfigMap |
| `docs.enabled` | serves the documentation site |
| `web.resources` | the web tier's requests and limits |

## Application environment

| Variable | Read as |
| --- | --- |
| `FC_ORG` | the GitHub organisation the console acts in; required |
| `FC_WORKER_IMAGE` | the full worker image reference; rendered from `images.worker` |
| `FC_DOMAIN` | the install's public domain, for studio hosts and links |
| `FC_LIVE` | `1` activates the in-cluster settings and credential stores |
| `FC_DRIVE_LIVE` | `1` lets a drive submit real workflows |
| `FC_REPOSITORIES` | the operators' repository scope; the organisation's repositories by default |
| `FC_PLATFORM_REPO` | the platform repository, whose fleet row reads as core |
| `FC_STUDIO_SVC_DOMAIN` | the cluster's service domain for the studios' internal doors |
| `FC_HOST` | the backend's listen address; loopback in the pod |
| `FC_PORT` | the backend's listen port |
| `FC_ARCHIVE_DIR` | where operation receipts are kept |
| `FC_RUN_LOG_DIR` | where terminal run logs are snapshotted |
| `FC_OIDC_ENABLED` | whether the sign-in proxy fronts the console |
| `FC_ADMIN_GROUP` | the identity-provider group whose members are the console's admins; set with OIDC on, it switches teams on |
| `FC_OIDC_ISSUER` | the issuer an operator principal is qualified with |
| `FC_PROXY_SECRET` | the secret the web tier proves itself with |
| `FC_LOCAL_OPERATOR` | the operator admitted on loopback when OIDC is off |
| `FC_EXECUTION_TOKEN` | the execution door's token |
| `FC_EXECUTION_PRINCIPAL` | the execution door's caller name |
| `FC_EXECUTION_REPOSITORIES` | the execution door's repository scope |
| `FC_NATS_SERVERS` | the event bus address, when events are enabled |
| `FC_NATS_CREDS` | the assembled bus credentials file |
| `FC_REACH_HELPER` | the pinned record helper's path |
| `FC_STAMP_HELPER` | the pinned gate stamper's path |
| `FC_ESTABLISH_HELPER` | the pinned scratch establisher's path |

## Read next

- [Deploy an install](../../operations/deploy/)
- [API conventions](../api/)
