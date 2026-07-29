# BOSS Tests

This folder contains unit tests for the BOSS mapping utilities:

- `test_mapper.py` — the agent tool layer in `mapper_agent.py`
- `test_ingest.py` — the `ingest.py` CLI used by the batch-ingest workflow
- `test_exception_alert.py` — the exception-alert helper

## Install test dependencies

From the repository root:

```bash
python3 -m pip install pytest
```

## Run the tests

From the repository root:

```bash
pytest -q BOSS/tests/test_mapper.py
```

If you want to run all tests under `BOSS/tests`:

```bash
pytest -q BOSS/tests
```
