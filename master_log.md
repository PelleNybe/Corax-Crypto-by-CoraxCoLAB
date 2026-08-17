# Master Log

## Task: 🧪 [testing improvement] Add missing test paths for strategy_loader

* Analyzed the gap and wrote additional tests in `tests/test_strategy_loader.py`.
* Verified with `poetry run pytest` and verified 100% coverage via `--cov=core.strategy_loader`.
* Ensured formatting and syntax was clean with `ruff`.
* Committed changes with the required `🧪 [testing improvement]` PR formatting.

## 2024-05-18 - [CRITICAL] Fix Path Traversal in API Backtest Endpoint
**Vulnerability:** The `/api/v1/backtest` endpoint accepted an unsanitized `data_path` parameter from the user payload and passed it directly to `VectorizedBacktester.run()`, which subsequently passed it to `pl.scan_parquet(data_path)`. This would allow an attacker to traverse the file system and scan arbitrary files on the system using relative paths like `../../../../etc/passwd` or `/etc/passwd`.
**Learning:** Even when inputs are destined for data analysis libraries like Polars (and not immediately displayed to the user), they can be abused for reading files (data exfiltration, SSRF-like local file inclusion, or crashing the server).
**Prevention:** All user-provided file paths must be validated using `pathlib.Path.resolve().is_relative_to()` to ensure they remain contained within the intended base directory.

## 2024-08-14 - Accessible Window Controls
**Learning:** Found that custom window components (like the strategy builder panel) used `<span>` tags instead of `<button>` for their close/minimize actions. These lacked semantic roles, keyboard focusability, and ARIA labels.
**Action:** Always replace non-interactive tags like `<span>` or `<div>` with semantic `<button>` tags when they are meant to trigger actions, and supply `aria-label`s. Also ensure that custom components retain styling when switching tags by adding appropriate base resets (`background: none`, `border: none`).
