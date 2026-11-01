# Production migration handoff

Updated: 2026-11-01.

The active successor is `Olbrasoft/series-to-prehrajto-2`, checked out at
`/home/jirka/Olbrasoft/series-to-prehrajto-2`. The former repository
`Olbrasoft/series-to-prehrajto-1` exceeded GitHub’s 100 GiB size quota; its production
workflows are disabled and uploads are paused. Never re-enable that repository.
Its history and the older `series-to-prehrajto` repository are preserved.

The seed comes from commit `91277e1744c70f0432a4d1827545714950036dd5`.
A verified snapshot is stored at
`/home/jirka/.cache/series-recovery-20261101/snapshot-91277e17.tar.gz`,
SHA-256 `52c28ed8175c3facd37678ce663ebc1b2d08498ed2ee59cbacf4f62489190561`.
Recovery logs and private validation reports are in the same protected directory;
never print or commit its credentials file.

Fifteen successful but uncheckpointed upload records (twelve distinct episodes)
were recovered from Actions logs and individually verified on the correct portal
accounts before merging into the successor state. Three extra target copies are
recorded in the private recovery report; no portal videos were deleted.

The two upload accounts remain olbrasoft.claudecode@gmail.com (shards 0/1) and
serialy.prehrajto@seznam.cz (shards 2/3). Alternate subtitle search stays paused.
Original-file size verification and Whisper checks from the predecessor remain
required. Always inspect current origin/main, actual upload timestamps and queue
counts; a green workflow alone does not establish progress.

Operational state still needs durable storage outside Git history. This migration
preserves data but must be accompanied by fail-closed upload checkpoints and less
frequent full exports. Do not force-push or delete predecessor history.

## Durable upload reservations

Before sending a video, the uploader must persist a `pending_uploads` reservation.
The Git ref is the shared claim boundary for all accounts and shards; committed
reservations win over new proposals. Pending episodes are excluded by the picker,
source preparation, Whisper review and manifest builder. Successful uploads close
the reservation through their normal uploaded episode record.

`StatePersistenceError` is fatal. Failed upload checkpoints are preserved as
private Actions artifacts named `upload-checkpoint-RUN-SHARD`. Pending entries
never expire automatically: download the artifact, verify the target on the
correct account, and merge a completed upload record before releasing one. Never
clear a reservation merely to increase the ready count. An interrupted upload
may already have created its target on the portal.

Full catalog exports are rate-limited to the existing three-hour cadence even
when the database contains fewer episodes than the requested upper limit. Backlog
gzip exports have deterministic headers, so unchanged data does not add a new
binary object solely because the export time or output filename changed.
