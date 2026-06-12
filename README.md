# speckle

<https://github.com/joeblew999/speckle>

Tooling for running [Speckle](https://speckle.systems/) (the AEC data platform)
locally and bridging it to fabrication. Extracted from the factory-floor project —
it's a standalone concern: a CAD/AEC pipeline, not part of the OPC-UA machine stack.

This repo is an **overlay**: the mise/pitchfork tooling and configs live here; the
heavy upstream Speckle server source is pulled into `speckle-server/src/`
(gitignored) by mise, the same pattern as our other `.src/` overlays.

## Sub-projects

| Dir | What | Stack |
|-----|------|-------|
| [`speckle-server/`](speckle-server) | run a local Speckle instance from source, native (no amd64 emulation) | node 22 · postgres 16 · redis · minio · pitchfork |
| [`speckle-watcher/`](speckle-watcher) | SketchUp → Speckle → Howick cut-list (CSV) converter | Python |
| [`speckle-docker/`](speckle-docker) | all-Docker fallback (slower on ARM) | docker-compose |

Upstream server: <https://github.com/specklesystems/speckle-server> (pinned via
`SPECKLE_VERSION` in `speckle-server/.mise.toml`).

## Run

Each sub-project has its own `.mise.toml`. From a sub-project dir:

```bash
mise run setup     # one-time: fetch upstream source, init data dirs
mise run start     # start the daemons (pitchfork)
```

See each sub-project's `README.md` for details. Secrets go in a local `.env`
(copy `.env.example`); never committed.

## Relationship to factory-floor

The `speckle-watcher` produces the Howick cut-list CSVs that
[factory-floor](https://github.com/joeblew999/factory-floor)'s gateway dispatches
to machines. The two are decoupled — Speckle is one possible job *producer*; the
factory stack doesn't depend on it.
