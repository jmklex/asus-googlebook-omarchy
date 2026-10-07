# Attribution and source boundaries

The Python toolkit, configuration assembly and documentation are original project work, released under MIT. The live and installed graphics startup scripts were extracted from the implementation tested on the physical ASUS Googlebook.

This repository does not redistribute Omarchy, an OS image, ASUS firmware, Wi-Fi credentials, SSH host keys, AVB private keys, disk backups or LUKS headers.

The build downloads pinned **source code** from these projects. They retain their licenses:

| Component | Source | License |
|---|---|---|
| Android boot-image tools | [AOSP mkbootimg](https://android.googlesource.com/platform/system/tools/mkbootimg/) | Apache-2.0 |
| Android Verified Boot | [AOSP libavb / avbtool](https://android.googlesource.com/platform/external/avb/) | MIT/BSD and Apache-2.0 components; see upstream license files |
| Firmware loader validator | [ChromiumOS vboot_reference](https://chromium.googlesource.com/chromiumos/platform/vboot_reference/) | BSD-style and upstream component notices |
| OS and applications, obtained separately | [Omarchy](https://github.com/omacom/omarchy), [Arch Linux](https://archlinux.org/) | Each package's license |

`tools/loader_harness.c` is a modified ChromiumOS test utility, governed by `tools/LICENSE.chromium`. It is a host simulation of the Android loader in developer mode, not ASUS firmware or a replacement firmware image. Its disk-write callback deliberately does not write.

The audio diagnosis used the Linux Lapis board quirk and SOF topology sources. The [ExpertBook audio notes](https://github.com/burakgon/asus-expertbook-linux/tree/main/audio-fix) helped identify the matching `1043:15e4` speaker tuning. That project's patcher and firmware blobs are not incorporated. ExpertBook firmware must not be flashed onto a Googlebook.

Source revisions are fixed in `tools/fetch_sources.py`. Generated live images contain the source and licenses of those fetched build tools so native boot images can be assembled without another network download.
