# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-06-11

### Added
- **Pre-commit hook** — `.githooks/pre-commit` runs `pytest` before each commit,
  preventing broken code from entering the repository.

### Fixed
- `save_mappings` output now includes `confidence` and `reasoning` fields (#7).
- NaN column names no longer cause mapping failures.
- `AgentLoopError` on timeout is handled gracefully.
- Canonical field validation errors resolved.
- Empty input files and numeric XLSX headers are handled correctly.
- Partial mapping saves no longer corrupt output (#4).

### Changed
- Hardened `mapper_agent` against real-world spreadsheet edge cases (#3).

## [2.0.0] - 2026-06-08

### Added
- **BOSS field mapper** — a Claude-powered tool that maps source fields to a
  target schema (`BOSS/mapper_agent.py`), including an autonomous agent loop
  that calls tools to produce the mapping.
- **Data ingestion** — `BOSS/ingest.py` for reading source data into the
  mapping workflow.
- **Sample data and output** — `BOSS/sample.csv` and the generated
  `BOSS/sample.mapped.json` demonstrating an end-to-end mapping, now including
  the `VendorID` field.
- **Test suite** — `BOSS/tests/test_mapper.py` with detailed `mapper_agent`
  tests, plus `BOSS/tests/README.md` documenting how to run them.
- **Continuous integration** — `.github/workflows/test.yml` runs the test
  suite on every push/PR (the "Run tests" status check), with a documented
  step-by-step workflow.
- **Dependency manifest** — `requirements.txt` listing project dependencies.
- **Documentation** — `BOSS/README_BOSS.md` describing the mapping workflow
  and the `mapper_agent.py` usage.

### Changed
- Fixed the `mapper_agent` tool loop so it terminates correctly and produces
  stable mapping output.
- Corrected agent path resolution so the agent runs reliably regardless of the
  working directory.
- Renamed the top-level `README.md` to `README_brief.md`.

## [1.0.0] - 2026-05-21

### Added
- **Claude API summarizer** — `brief.py`, the initial command-line tool that
  summarizes input using the Claude API.
- **Text file input** — read the content to summarize from a `.txt` file
  (`financial_data.txt` sample included).
- **CLI flags** — options to control output format and to save the result.
- **Documentation** — `README.md` with usage instructions.
- **Project scaffold** — initial repository structure and `.gitignore`.

[3.0.0]: https://github.com/shivakvasar/ai-projects/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/shivakvasar/ai-projects/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/shivakvasar/ai-projects/releases/tag/v1.0.0
