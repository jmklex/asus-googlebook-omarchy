# Contributing

Start with a discussion in a GitHub issue and identify the exact board, firmware and stage. Use a sanitized geometry report for a proposed new capacity profile. Do not post full hardware dumps, device serials, UUIDs, Wi-Fi details, network addresses, raw recovery logs or partition backups.

Keep image construction separate from raw device writes. Every write must have explicit device selection, current identity checks, exact bounds, a backup, read-back and a documented recovery path. Guards use runtime checks, never Python assertions that disappear under `-O`.

Run `python3 -m unittest discover -s tests -v`, repeat with `python3 -O`, and run `python3 tools/check_public.py` after staging changes. Firmware-loader validation and QEMU tests are useful but must not be reported as physical hardware results. Describe what was actually tested and on which SKU/firmware.

Do not weaken package verification, add shared credentials, publish per-device files, or silently generalize hardware-specific quirks. Keep GPL firmware/kernel and third-party source licensing separate from this repository's original MIT code.
