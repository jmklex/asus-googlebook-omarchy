# Hardware support and boundaries

Evidence date: 7 October 2026. **One physical laptop**, ASUS Googlebook 14 CX9406CAA, DMI `Google / Lapis`, 512 GB internal NVMe, firmware `Google_Lapis.16650.184.0`, factory build `CL3B.260622.271.R1`. Kernel: `7.2.4-arch1-Watanare-T2-3-t2`, from Omarchy 4.0.4. These are observed versions, not claims about the latest releases.

| Feature | Evidence |
| --- | --- |
| Internal boot, USB removed | Full encrypted-root Omarchy boot and subsequent reboot passed |
| Live USB cold start | Desktop recovered with the checked Xe unload/reload sequence |
| Internal display | BOE NB140B91-M04, 2880×1800, scale 2; 60 Hz and 120 Hz desktop visually checked |
| Hardware rendering | Mesa shader and pixel-readback test passed |
| Keyboard and touchpad | Used interactively |
| Wi-Fi and DNS | Connected, resolved names and reached external services |
| Internal storage and encryption | LUKS2 password unlock, Btrfs root; boot writes read back |
| Speakers | Owner heard playback; audio correction survived reboot |
| Snapper | Filesystem snapshot creation and cleanup passed |
| Microphone, headphones, Bluetooth audio | Not physically tested |
| Camera, external displays, suspend/resume | Not tested |
| Battery life / thermal tuning | Not validated |
| 120 Hz | Active mode verified; owner confirmed steady image during timed testing and subsequent scrolling/window movement with AirPlay disconnected. Brief flashes occurred at refresh-rate changes. Installer default remains 60 Hz. |
| Full Omarchy upgrade | Not performed; kernel is pinned and guarded |
| Factory restore | Recovery USB created and read back; actual restore not exercised |
| Other capacity, SKU, firmware | Unsupported until independently validated |
| Fresh public-script installation | Not yet physically completed; original manual/staged procedure is the hardware evidence |

The similar-looking ASUS ExpertBook B9406CAA is a different firmware platform. Its Linux audio research was useful, but neither its BIOS nor its patcher is used here. Other Googlebook brands are outside scope.

The 120 Hz check used the existing display workarounds, VRR disabled and an XRGB8888 compositor buffer. It produced no new kernel log messages during the timed switch test. This establishes operation during the observed desktop session, not 120 Hz cold-boot, suspend/resume or AirPlay compatibility. See [maintenance.md](maintenance.md#refresh-rate) for the setting and 60 Hz fallback.

The native profile intentionally compares all partition labels, offsets, sizes and types. Device-specific disk and partition UUIDs are discovered locally. A 1 TB machine, modified factory layout, changed active slot or previously installed machine should refuse the fresh-install path. Do not make a failing check pass by changing identifiers.

This project uses developer mode and user-generated AVB keys. AVB verification here checks image integrity/packaging; it does not restore the factory locked-boot security model. Disk encryption protects userdata at rest, but the boot partitions remain writable outside that encryption.
