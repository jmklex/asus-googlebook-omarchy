# Native encrypted installation

**This replaces Googlebook OS and erases userdata.** The staged scripts are a generalized experimental version of the procedure proven on one device. Read this page through first. Have a working live USB, separate factory recovery media, personal-file backups, external backup storage, AC power and time to investigate a failed stage. Do not use the stock Omarchy installer or repartition the whole disk.

Commands below run as root from the successful live session. The kit is already included at `/opt/asus-googlebook-omarchy`. The internal device name is an explicit input; check it with `lsblk`. The example `/dev/nvme0n1` is typical, not an instruction to skip identification.

## 1. Inspect and back up

```sh
sudo -i
cd /opt/asus-googlebook-omarchy
python3 tools/native.py plan --device /dev/nvme0n1
```

This reads DMI, the live environment, the disk and both GPTs. It requires the tested 512 GB Lapis geometry, a successful preferred slot A and intact original `pvmfw_a/b` labels. It records your disk's actual GUIDs rather than shipping someone else's. A mismatch is a stop condition, not an invitation to edit the profile.

Mount your **separate external backup filesystem** at a path you choose, for example `/run/media/backup`. Confirm its disk identity. The path must be a real external block filesystem, not the live overlay, the live image partition or internal userdata. Then:

```sh
python3 tools/native.py backup --destination /run/media/backup/lapis-original
python3 tools/native.py verify-backup /run/media/backup/lapis-original
```

The backup contains both GPTs and all small device/boot/recovery partitions. It deliberately excludes `userdata` and the large `super` partition. **It is neither a backup of your files nor a full factory image.** Keep the verified factory recovery USB too. Backups contain private device material: do not put them in Git, public cloud folders or issues. Make another private copy when possible. Keep this external volume mounted for the entire installation.

State lives in `/run/lapis-install` until the successful boot commit copies it to encrypted storage and the external backup. Do not reboot midway. If a stage fails, see [recovery](recovery.md); markers prevent destructive blind retries.

## 2. Format only userdata

```sh
python3 tools/native.py format
python3 tools/native.py format --apply
```

The first command is a dry run. The second rechecks the disk, AC, backup, mounts and holders, then requires the exact phrase shown. It asks for a new disk password locally. The password is supplied to cryptsetup through stdin, not stored in the image or passed in command arguments. Use a memorable strong password; there is no recovery key in this project.

This creates LUKS2 (Argon2id) and Btrfs subvolumes `@`, `@home`, `@log`, `@pkg`, mounted under `/mnt`. It writes a private LUKS header backup to the external drive. Keep that header protected: together with a password valid when it was saved, it can unlock the encrypted volume even after later key changes.

## 3. Install and configure Omarchy

Choose your own Linux username, display name, timezone and console keyboard map. These values are examples:

```sh
python3 tools/configure_target.py packages --user alex --name 'Alex' --timezone Europe/London --keymap us
python3 tools/configure_target.py configure
```

The package stage uses the ISO's offline mirror, installs the full base/application manifest and Omarchy runtime, and runs official system/user provisioning. Normal packages require trusted signatures. The two kernel packages are the exact checksum-pinned ISO files, whose local detached signatures are unavailable; that exception is confined to their local installation command.

You choose a separate login/sudo password through a local prompt. Root password login is locked. The installed session automatically opens after you unlock the encrypted disk, matching the tested configuration. Wi-Fi passwords are not transferred from the live session: connect using the installed desktop's network menu or `nmtui` after boot. SSH is masked by default.

Configuration applies the Lapis graphics/audio sequence, 2880×1800 at 60 Hz with scale 2, the small encrypted-root initramfs, a kernel pin and transaction guard, and the changes needed to keep factory EFI discovery and Limine integration from breaking startup.

## 4. Build and validate the native boot set

The source dependencies are already included in the live kit. The compiler is installed inside the target; build a Linux-native loader there:

```sh
mkdir -p /mnt/opt/lapis-kit
cp -a /opt/asus-googlebook-omarchy/. /mnt/opt/lapis-kit/
arch-chroot /mnt python3 /opt/lapis-kit/tools/build_loader.py
python3 tools/native.py build
python3 tools/native.py validate --loader /mnt/opt/lapis-kit/build/load_android_test
```

The candidate uses the target's actual LUKS UUID and a fresh local signing key. It places the compressed initramfs in `vendor_boot_a`, pads its end to four bytes, and keeps an empty generic ramdisk in `init_boot_a`. It fits and signs the four factory-sized slot-A images, then tests a sparse copy of the proposed disk layout through the ChromiumOS Android loader. Sparse validation files contain no userdata.

Loader success checks packaging and selection, not the physical boot or the password prompt. The original development also tested encrypted-root boot in QEMU; that historical result does not validate your newly created device. Keep recovery available for the first physical boot.

## 5. Review and commit

```sh
python3 tools/native.py commit
python3 tools/native.py commit --apply
```

The dry run verifies the candidate against its validation record and the original bytes against the private backup. Apply requires a second explicit typed phrase. It writes and reads back only the four slot-A images, the two GPT regions with `pvmfw` label changes, and a single misc sector preserving bytes after the 32-byte command. On an ordinary write/verification exception, it attempts to restore every attempted region and saves the result. This cannot make a power loss safe: keep AC connected and the recovery USB ready.

A successful commit archives state under `/var/lib/asus-boot/installation` on the installed system and `installed-state` beside the external backup. The AVB key is kept on encrypted root and in that private external archive. Confirm both archives exist before shutdown.

```sh
sync
umount -R /mnt
cryptsetup close omarchy_root
poweroff
```

Remove the live USB and backup drive. Start the laptop and choose **Boot from internal disk** in developer mode. Type your LUKS password at the text prompt. Do not relock the bootloader.

## 6. First-boot acceptance

Check the desktop, keyboard/touchpad, network, speakers at a modest volume, and these diagnostics:

```sh
findmnt /
uname -r
systemctl --failed
systemctl status asus-gpu-prepare.service
hyprctl configerrors
wpctl status
sudo snapper -c root list
```

The root should be Btrfs on `omarchy_root`; the kernel should match the pinned version; graphical configuration and services should be healthy. Once satisfied, create a baseline snapshot with `sudo snapper -c root create --description 'Lapis initial working installation' --cleanup-algorithm number`, then check `sudo systemctl start snapper-cleanup.service`. Test another restart and a cold boot with the USB removed before calling the installation complete. Keep both recovery drives and the private backups. Read [maintenance](maintenance.md) before updates.
