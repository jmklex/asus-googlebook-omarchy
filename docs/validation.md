# Validation record

## Physical evidence: original procedure

On 7 October 2026, one 512 GB ASUS CX9406CAA / Google Lapis completed the original staged installation. The full Omarchy desktop booted from the internal encrypted drive with USB removed. The owner confirmed the desktop and audible speaker playback. A subsequent internal boot retained the display, Wi-Fi and audio fixes and had no failed systemd units. A graphics shader/pixel-readback test, Snapper snapshot creation and snapshot cleanup passed.

The working live USB also passed a restart and cold-start graphics test. Before internal installation, the Android loader accepted the native candidate, a disposable encrypted-root QEMU fixture reached its init program, and each committed disk region passed read-back. Original logs and disk backups remain private; they are not included here.

## Public repository checks

The generalized source toolkit is tested separately from that original installation:

- Python safety tests cover corrupted GPT headers/entries, overlapping/out-of-bounds partitions, duplicate labels, minimal label renaming, USB capacity relocation, refusal of device/existing/symlink outputs, CPIO overrides/path rejection, unsupported layouts and short writes.
- An injected partial boot-write failure checks restoration of **every attempted region**, including the partly written region.
- The tests pass both normally and under `python3 -O`, confirming safety checks do not depend on assertions.
- The ChromiumOS loader harness builds from pinned upstream source on macOS, including from the exact filtered source payload embedded in the live image.
- A complete live image was built from the checksum-pinned ISO. AVB signature/hash verification passed for all boot components, both GPTs validated, and `vb2api_load_kernel() returned 0` on the final disk image.
- QEMU booted the loader-assembled live ramdisk and read-only USB image through to the live serial login in 39 seconds, with no initramfs unpacking error and no network attached. The hardware-specific desktop service is expected to reject a VM's non-Lapis identity; this validates the boot/archive/live-root path only.
- Tracked-file checks reject common secret material, private local paths, oversized files and disk/key artifacts. A manual review complements those checks; pattern scans are not a guarantee against every possible secret.

GitHub Actions runs the safety suite and loader build on Linux and macOS. See the Actions tab for actual results of the current commit. The multi-gigabyte ISO and physical boot are not part of CI.

## Not established by these checks

The generalized public installer has **not** completed a second fresh physical installation. The public USB writer has not been used to overwrite the already-working test drive. No generalized-script test authorizes writes to a different board, firmware or capacity. The original laptop was not reinstalled merely to publish this repository.

This release does not claim suspend/resume, camera, microphone capture, external displays, Bluetooth/headphone playback, battery-life tuning, a complete future update path or a tested factory restore. See [support.md](support.md) for the full matrix.
