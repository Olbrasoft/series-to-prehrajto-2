# Public repository security preflight

2026-11-01: publication remains blocked pending credential and history cleanup.

The repository is private. A full-history review included all remote branches,
tags and pull-request refs (360 commits, 776 unique blobs), gzip-expanded state,
the migration release attachment, the external subtitle artifact and 318 Actions
log archives. The Git-diff scanner missed the custom proxy shared secret; scanning complete
blob contents found five instances. Exact comparison against documented live
credentials found `CZ_PROXY_KEY` inside old
proxy failure URLs: 164 historical blob versions and all five current upload
state files. Never copy the value into an issue, report, console or PR body.

The current-state cleanup preserves uploads, reservations and failure records.
The merge/save boundary redacts credential-bearing query parameters, including
encoded nested URLs. Search failures preserve HTTP status and exception type
without including the request URL. Login and upload diagnostics no longer print
cookie values, login bodies, upload nonces or CDN signatures. The regression
suite passes 201 tests locally.

A mirror of all original remote refs and downloaded log archives is retained
privately under `/home/jirka/.cache/series-public-audit-20261101`. An offline
filtered mirror is being prepared for review. No remote history has been
rewritten, no logs have been deleted and no shared server credential has been
changed. GitHub pull-request/cached commit views can retain original objects even
after a branch force-push. Before publication, reconcile those views and revoke
or rotate the exposed shared credential across all dependent services. A normal
cleanup commit is insufficient for publishing a repository containing a live
credential in historical refs.

Historical upload logs also contain scoped upload nonces/signatures and
ancillary cookie values. Treat these logs conservatively before making
them public; backups are retained. Exact credential comparison and Gitleaks
found no configured persistent credentials in the downloaded logs or subtitle
release/artifact archives. This does not replace server-side invalidation of
credentials discovered in repository history.

## Remediation completed before publication

The owner explicitly approved shared credential rotation, dependent-client
updates, backed-up log removal and remote history rewriting on 2026-11-01.
The predecessor repository `series-to-prehrajto-1` was already public: an
anonymous HTTP request independently confirmed the live credential in its legacy
state. Server-side invalidation was therefore necessary independently of this
successor's visibility.

The proxy's ignored server configuration, six configured repository secrets,
local access documents and the production web consumer were updated together.
An HTTP check proves that the old credential returns 403 and the replacement
returns 200 with a playable video configuration. The running web container was
independently checked to use the replacement; the database was not modified.
Other candidate repositories were inspected and had no matching proxy secret.
Two dependent upload clients also needed diagnostic fixes to avoid leaking the
replacement through request exceptions or response bodies. Their original local
working changes were preserved by using separate worktrees.

Original Git refs, release/artifact copies and 318 downloaded log archives remain
in the private audit directory. Five run log sets containing authentication
response diagnostics were selected for removal from GitHub after backup. Normal
workflow records and durable upload/subtitle state are preserved. Cached PR views
may retain the revoked historical key; it no longer grants access. The new key
must never be included in the rewritten Git history or audit reports.
