# Boot and hardware notes

Lapis retains Google's Depthcharge firmware. Its Android boot path selects GPT `vbmeta` slots, verifies AVB metadata and loads Android v4 boot components. An ordinary x86 UEFI ISO layout does not describe the native internal installation.

## Image layout

- `boot_a`: the tested Linux kernel and command line; 64 MiB factory region.
- `init_boot_a`: a small empty generic CPIO; 8 MiB factory region.
- `vendor_boot_a`: the compressed encrypted-root initramfs in a platform fragment; 32 MiB factory region.
- `vbmeta_a`: signed descriptors for all three; 4 MiB factory region.
- `userdata`: LUKS2 containing Btrfs. The password is typed at boot, never embedded in the boot images.

The live USB needs a much larger initramfs and uses generated, larger Android partitions appended after the original ISO filesystem. Its payload is in `init_boot_a`. Both paths preserve the exact kernel SHA-256 from the pinned ISO.

The loader concatenates vendor and generic ramdisks without adding Linux archive padding. A compressed vendor ramdisk whose length is not a multiple of four can leave the next CPIO header misaligned. The builder explicitly adds zero padding before packaging. The corrected assembled ramdisk passed encrypted-root QEMU boot and then physical boot during original development.

The factory `pvmfw_a/b` labels select Android protected-VM firmware in the loader. The installation renames only those two labels to `factory_pvmfw_a/b`; their payloads, GUIDs, geometry and attributes are retained. Both GPT header and entry CRCs are regenerated. It also clears only the 32-byte `misc` boot command so a stale recovery request cannot override normal boot. The rest of `misc` is preserved.

## Graphics and audio

The panel needed a normal Xe load/unload/reload before any graphical client started. The service releases framebuffer console references, waits for module references to clear, and refuses forced unload. It disables the observed-problematic display power features and uses `AQ_NO_MODIFIERS=1` and `AQ_NO_ATOMIC=1`. The conservative tested mode is 2880×1800 at 60 Hz.

SOF audio holds a graphics-module reference. Its PCI driver must bind after the graphics reload; soft blacklisting plus `ExecStartPost` enforces that order. The Lapis topology correction then removes unsupported PCH-DMIC links while preserving speaker/codec and SSP2 Bluetooth-offload descriptors. Both packaged CS35L56 ASUS amplifier tunings loaded on the tested unit.

## Upstream references

- [AOSP mkbootimg](https://android.googlesource.com/platform/system/tools/mkbootimg/) and [AVB](https://android.googlesource.com/platform/external/avb/).
- [ChromiumOS vboot](https://chromium.googlesource.com/chromiumos/platform/vboot_reference/) and [Depthcharge](https://chromium.googlesource.com/chromiumos/platform/depthcharge/).
- [Linux v7.2 SOF SoundWire board quirks](https://github.com/torvalds/linux/blob/v7.2/sound/soc/intel/boards/sof_sdw.c) and [Panther Lake topology matching](https://github.com/torvalds/linux/blob/v7.2/sound/soc/intel/common/soc-acpi-intel-ptl-match.c).
- [ExpertBook audio research](https://github.com/burakgon/asus-expertbook-linux/tree/main/audio-fix), useful for the matching codec subsystem. Its patcher and firmware images were not applied to the Googlebook.
- [Omarchy](https://github.com/basecamp/omarchy). System and user provisioning remain official Omarchy code from the pinned ISO.

Pinned build-source commits and license boundaries are recorded in [NOTICE.md](../NOTICE.md). A compatible future upstream kernel may remove these workarounds; this repository does not claim compatibility without another physical test.
