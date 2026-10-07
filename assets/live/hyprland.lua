-- Diagnostic desktop only, stored in the live RAM overlay.
hl.monitor({ output = "eDP-1", mode = "2880x1800@60", position = "0x0", scale = 2 })
hl.env("XCURSOR_SIZE", "24")
hl.config({
    general = { gaps_in = 6, gaps_out = 18, border_size = 2 },
    decoration = { rounding = 6, blur = { enabled = false }, shadow = { enabled = false } },
    animations = { enabled = false },
    misc = { disable_hyprland_logo = true, force_default_wallpaper = 0, vrr = 0 },
    input = { kb_layout = "us", touchpad = { tap_to_click = true } },
})
hl.on("hyprland.start", function ()
    hl.exec_cmd("foot --config=/dev/null --title='ASUS Lapis live graphics test' -f 'Liberation Mono:size=15' bash --noprofile --rcfile /home/asuslive/live-bashrc")
end)
hl.bind("SUPER + Return", hl.dsp.exec_cmd("foot"))
hl.bind("SUPER + Q", hl.dsp.window.close())
