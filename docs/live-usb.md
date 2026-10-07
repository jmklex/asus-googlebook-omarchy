# Build and test the live USB

## 1. Prepare recovery and unlock

Back up personal files first and create the separate [Googlebook recovery drive](recovery.md). Unlocking wipes the device. Do this before experimenting with Linux.

Google's [bootloader-unlock instructions](https://support.google.com/googlebook/answer/17389679), checked 7 October 2026, describe enabling Developer options by selecting Build number seven times in About device, then enabling OEM unlocking under System → Advanced → Developer options. With peripherals disconnected, hold Esc + F2, tap Power, and release the keys when the screen lights. Choose Advanced options → Unlock bootloader and follow the prompts. Follow the current official page if its instructions change.

Leave developer mode enabled while using this installation. The tested firmware offers **Boot from external drive** on the developer startup screen. The recovery screen's USB option is for factory recovery, not this Linux image. If the external boot option is absent, stop; this project does not supply a firmware-unlock bypass.

## 2. Build on macOS or Linux

Use Python 3.10+, Git, OpenSSL, zstd, bsdtar/libarchive, make and a C compiler. On macOS, install the Xcode command-line tools and, if using Homebrew, `brew install python zstd`. macOS supplies bsdtar and a usable OpenSSL-compatible command. On Debian/Ubuntu, use `sudo apt install python3 git openssl zstd libarchive-tools build-essential`. Allow approximately 20 GB of free working space. The ISO download is about 6 GB.

```sh
git clone https://github.com/jonathankleiman/asus-googlebook-omarchy.git
cd asus-googlebook-omarchy
mkdir -p downloads build
curl --fail --location --output downloads/omarchy-4.0.4.iso https://iso.omarchy.org/omarchy-4.0.4.iso
python3 tools/fetch_sources.py
python3 tools/build_loader.py
python3 tools/build_live.py --iso downloads/omarchy-4.0.4.iso --output build/lapis-live.img
```

The builder requires this exact ISO SHA-256:

```text
ddeded2758c48318d201dfdac905ecb28f570441883f0c052ea3cd5d05acf92d
```

It rejects changed downloads instead of silently accepting a newer ISO. If that version disappears, do not substitute another without revalidating the kernel, firmware and package set.

Validate the final image with the firmware's Android loader:

```sh
cd build
./load_android_test -b 1 lapis-live.img
cd ..
```

Expect `vb2api_load_kernel() returned 0`. This is a host-side loader check. It does not prove display or storage support on your laptop. The harness writes an assembled `loaded-ramdisk.img` in its working directory but opens the disk image read-only.

## 3. Write a dedicated USB

Unplug other removable storage. Identify the **whole USB disk** using `diskutil list external physical` on macOS or `lsblk -d -o PATH,SIZE,MODEL,TRAN` on Linux. Never use a partition or the internal NVMe. Replace the placeholder below with the disk you have positively identified:

```sh
# macOS example placeholder; substitute your actual disk number.
sudo python3 tools/write_usb.py --image build/lapis-live.img --device /dev/diskN
sudo python3 tools/write_usb.py --image build/lapis-live.img --device /dev/diskN --apply

# Linux equivalent placeholder:
# sudo python3 tools/write_usb.py --image build/lapis-live.img --device /dev/sdX
# sudo python3 tools/write_usb.py --image build/lapis-live.img --device /dev/sdX --apply
```

The first command only checks. The apply command displays the target, requires `ERASE /dev/…`, unmounts it, erases it, verifies the written image, then moves the backup GPT to the USB's actual end and verifies both tables. Do not remove the USB before success. Eject it normally afterwards. Dismiss macOS's initialize-disk prompt. Do not use this drive for your private backup.

## 4. Physical live test

Connect AC, insert the USB and choose **Boot from external drive**. The image prepares a minimal Hyprland desktop in RAM, with a terminal on Super + Return and a root console on Ctrl + Alt + F1. Initial preparation installs packages from the USB and can take a few minutes. It deliberately disables the stock Omarchy installer.

At the root console:

```sh
cat /sys/class/dmi/id/product_name
uname -r
lsblk -o NAME,SIZE,TYPE,FSTYPE,MODEL,TRAN,MOUNTPOINTS
systemctl status lapis-live-prepare.service asus-live-desktop.service
iwctl
```

The board must be `Lapis`, kernel `7.2.4-arch1-Watanare-T2-3-t2`, internal disk unmounted, and display/input usable. In interactive `iwctl`, use `device list`, then `station YOUR_INTERFACE scan`, `station YOUR_INTERFACE get-networks`, and `station YOUR_INTERFACE connect YOUR_SSID`. Enter your Wi-Fi password at its private prompt. Interface names vary. Check DNS/network access with `curl -I https://omarchy.org`.

Perform both a restart and a full shutdown/power-on live test before installation. A black display, failed graphics preparation, missing storage, or non-working keyboard is a stop condition. Save narrowly scoped diagnostics privately; do not blindly upload complete journals. The live desktop does not enable the installed audio fix automatically.

If all checks pass, continue to [native installation](install.md). Until then, do not run any native `--apply` command. The live image and its local administrator account are for trusted physical testing, not daily use.
