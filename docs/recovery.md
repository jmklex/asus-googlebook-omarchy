# Recovery and failed stages

## Prepare before unlocking

Use Google's [Device Recovery Utility](https://chromewebstore.google.com/detail/device-recovery-utility/pocpnlppkickgojjlmhdmidojbmbodfm) and [Googlebook recovery instructions](https://support.google.com/googlebook/answer/17452429). Select the Googlebook device family and **ASUS Googlebook 14**; do not select an ExpertBook or a different Googlebook manufacturer. Keep that USB separate from the Linux live USB and your personal backups.

The original development created official Lapis recovery media and independently read back the written bytes. A factory restore was not tested on the installed laptop. Having a checksum-verified recovery drive is preparation, not proof of a successful future restore.

## A command failed before reboot

Stop at the first error and preserve `/run/lapis-install` on your private external storage. Keep the successful live session running. Read the precise error and any `rollback.json`; do not remove stage markers or repeat `format --apply` to fix an unrelated package failure.

- Before formatting: the original internal disk is unchanged by plan/backup stages.
- After formatting but before boot commit: userdata is already replaced; factory OS is no longer intact, even though its boot partitions are unchanged.
- After a failed commit: check each rollback record. The script attempts to restore all attempted boot regions, including a partially written one. This does not restore erased userdata. A power loss cannot be handled by exception rollback.
- After a successful commit: private state is on encrypted root and the backup drive. The tool refuses another fresh commit against the modified GPT.

Package or configuration recovery is a manual expert operation in this initial release. Use the saved markers, package logs and mounted target to identify the last completed step. Do not run the entire installer again. If you are unsure, save private evidence and use factory recovery to start over.

## Installed Linux will not boot

Choose external boot with the known-working live USB. Do not select bootloader relock or reset as an experiment. Identify internal userdata by its current label/UUID and verify the disk before opening it:

```sh
lsblk -o PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS
# Replace the placeholder with the verified userdata partition.
cryptsetup open /dev/VERIFIED_USERDATA omarchy_root
mount -o subvol=@ /dev/mapper/omarchy_root /mnt
```

For inspection, the installed logs are under `/mnt/var/log`, saved boot state under `/mnt/var/lib/asus-boot/installation`, and configuration under `/mnt/etc/asus-boot`. Mount the other subvolumes before a chroot that needs them. Never paste the contents of the AVB private key, LUKS header, saved network profiles or device-partition backups into an issue.

Restoring an original GPT or boot image requires verifying the backup's disk identity, exact offset, length and hash against the intended drive. This release does not expose a generic `dd` rollback command: it would be too easy to write a backup from another laptop. Use the recorded `plan.json` and a reviewed region-by-region restore, or use Google's complete factory recovery flow. Restoring boot/GPT bytes alone cannot undo a LUKS reformat.

## Returning to Googlebook OS

Copy any Linux files you need off the encrypted drive, then follow Google's current full recovery procedure using the dedicated ASUS media. Recovery erases local data. Complete a working factory boot before following any official relock instructions. Keep original device backups until recovery is confirmed.

No part of this project writes firmware flash, changes firmware write protection, or installs an ExpertBook BIOS.
