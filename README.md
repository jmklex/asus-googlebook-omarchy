# Omarchy on ASUS Googlebook

An experimental route to native **Omarchy 4.0.4 on ASUS Googlebook 14 (CX9406CAA / Google Lapis)**, using the factory firmware and an encrypted internal drive.

The original procedure booted a full Omarchy desktop from the internal 512 GB NVMe with the USB removed. Display, keyboard/touchpad, Wi-Fi, hardware rendering and audible speaker playback were verified on one laptop on **7 October 2026**, including a subsequent internal boot. This repository turns that work into a reproducible image builder, staged installation tools and recovery documentation.

**Early experimental release.** The generalized installation scripts have not yet completed a fresh installation on a second laptop. Do not treat software tests or a successful image build as another physical installation. Start with the live USB and stop if your hardware differs. This is a community project, unaffiliated with ASUS, Google or Omarchy.

## Start here

1. Read [support and limitations](docs/support.md). Only the tested **512 GB Lapis partition layout** is accepted by the native installer.
2. Back up your files and make a separate [factory recovery USB](docs/recovery.md).
3. [Build and test the live USB](docs/live-usb.md). This stage runs in RAM; it does not install to the internal drive. Bootloader unlocking itself erases factory user data.
4. After a successful live test, follow [native encrypted installation](docs/install.md).
5. Keep the recovery media and read [updates and troubleshooting](docs/maintenance.md).

You need an advanced Linux workflow, a second computer, a dedicated live USB (16 GB or larger), separate Googlebook recovery media, and external storage for private backups. A stock Omarchy full-disk installation is incompatible with this boot path.

## How it boots

```text
Factory Depthcharge firmware, developer mode
  → AVB-signed Android v4 boot / init_boot / vendor_boot / vbmeta, slot A
  → Linux 7.2.4 + small initramfs + typed LUKS password
  → encrypted Btrfs root → Lapis graphics/audio setup → full Omarchy desktop
```

No replacement firmware, ExpertBook BIOS, or UEFI conversion is involved. Installation formats `userdata`, replaces the four slot-A boot images, renames the two `pvmfw` GPT labels, and clears only the pending Android recovery command. Partition offsets and sizes stay intact. Slot B remains backed up and unmodified, but **is not a working factory-OS fallback after userdata is reformatted**.

The board needs a checked Xe driver reload before graphical clients start, with SOF audio loaded afterwards. Audio uses a topology-specific quirk. The boot images also require a four-byte boundary between concatenated ramdisks. See [technical notes](docs/architecture.md).

## Included

| Component | Purpose |
| --- | --- |
| `tools/build_live.py` | Build from one checksum-pinned official ISO; no raw disk access |
| `tools/write_usb.py` | Explicit USB selection, preflight, typed confirmation and read-back |
| `tools/native.py` | Hardware/layout checks, private backup, format, boot build, validation and commit |
| `tools/configure_target.py` | Full ISO package set, official Omarchy provisioning and Lapis configuration |
| `assets/installed/` | Graphics service and small encrypted-root initramfs configuration |
| `tools/build_loader.py` | Build a read-only ChromiumOS Android-loader harness |
| `tests/` | Corrupt-GPT, output-boundary, archive and write-failure checks |

Builds download pinned public source dependencies. No disk passwords, Wi-Fi profiles, SSH keys, device backups, disk GUIDs or private logs are shipped. Fresh local AVB signing keys are generated per build. The live image has a local root console and passwordless live sudo; SSH is disabled by default. The installed system has a locked root password, password-protected sudo, disk encryption and no enabled SSH service.

## Contributing

Report the exact SKU, firmware version, storage capacity, stage and visible result using the issue templates. Keep serial numbers, network names, addresses, disk UUIDs, passwords and backups out of issues. New capacity/layout support needs actual device evidence and recovery testing; do not remove the guards to force an install. See [CONTRIBUTING.md](CONTRIBUTING.md).

[Validation record](docs/validation.md) separates physical evidence from repository checks.

## License and attribution

The original project code and documentation use the [MIT License](LICENSE). You may use, modify and redistribute them, including commercially. Keep the copyright and license notice in copies or substantial portions.

Suggested credit: **Jonathan Kleiman — [Omarchy on ASUS Googlebook](https://github.com/jonathankleiman/asus-googlebook-omarchy)**. No additional permission or payment is required. This suggested wording adds no conditions to MIT.

The ChromiumOS-derived test harness and other upstream components retain their own licenses and attribution; see [NOTICE.md](NOTICE.md).
