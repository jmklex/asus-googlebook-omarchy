run_latehook() {
    mkdir -p /new_root/opt/asus-googlebook-omarchy /new_root/etc/modprobe.d /new_root/etc/modules-load.d
    cp -a /lapis-kit/. /new_root/opt/asus-googlebook-omarchy/ || return 1
    printf 'coreboot_table\nframebuffer_coreboot\ncorebootdrm\n' > /new_root/etc/modules-load.d/lapis-framebuffer.conf
    printf 'blacklist xe\nblacklist snd_sof_pci_intel_ptl\noptions xe gsc_firmware_path= enable_panel_replay=0 enable_psr=0 enable_fbc=0 enable_dsb=0 enable_sagv=0 enable_dc=0\n' > /new_root/etc/modprobe.d/lapis-live.conf
    mkdir -p /new_root/etc/systemd/system/multi-user.target.wants
    cp /lapis-kit/assets/live/prepare.service /new_root/etc/systemd/system/lapis-live-prepare.service
    ln -sf ../lapis-live-prepare.service /new_root/etc/systemd/system/multi-user.target.wants/lapis-live-prepare.service
    # This image never ships a shared SSH key, Wi-Fi password or machine ID.
    # Remote access remains off unless its owner explicitly configures it.
    ln -sf /dev/null /new_root/etc/systemd/system/sshd.service
    for unit in start quit quit-wait read-write switch-root; do
        ln -sf /dev/null "/new_root/etc/systemd/system/plymouth-$unit.service"
    done
    cat > /new_root/usr/local/bin/omarchy-iso-install <<'EOF'
#!/bin/sh
echo 'The stock full-disk installer is disabled on Lapis.'
echo 'Read the guide and use /opt/asus-googlebook-omarchy/tools/native.py instead.'
exit 1
EOF
    chmod 755 /new_root/usr/local/bin/omarchy-iso-install
    cat > /new_root/root/.automated_script.sh <<'EOF'
#!/bin/sh
printf '\nASUS Googlebook Lapis live test. The internal disk has not been installed.\n'
printf 'Guide: https://github.com/jonathankleiman/asus-googlebook-omarchy\n'
printf 'Root console: Ctrl+Alt+F1. Desktop terminal: Super+Return.\n'
printf 'Connect Wi-Fi with iwctl. Do not run the stock Omarchy installer.\n\n'
EOF
    chmod 755 /new_root/root/.automated_script.sh
}
