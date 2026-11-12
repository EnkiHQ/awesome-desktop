---
name: awesome-pet
description: Install, start, stop and customize the awesome-desktop desktop character, which types when the user types and clicks when the user clicks. Use when the user asks for a desktop pet / 桌面小人 / 小人按键盘按鼠标, wants it started on their computer, wants it to face them or turn its back, or wants it made from their own avatar.
---

# awesome-pet

A desktop character behind a little desk with a keyboard and a mouse. When the user presses a key, the nearer hand taps the same spot on the little keyboard; when the user moves or clicks the mouse, the right hand follows. Runs on macOS and Windows, detached from the shell that started it.

## Install and start

Needs `uv`. If it is missing, install it first (macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows PowerShell: `irm https://astral.sh/uv/install.ps1 | iex`).

```bash
uv tool install --force "awesome-desktop @ https://github.com/EnkiHQ/awesome-desktop/archive/refs/heads/main.zip"
awesome-pet start
```

If `awesome-pet` is not on PATH, run it from `$(uv tool dir --bin)`. `start` returns at once and the character keeps running after the shell or agent exits. It must run in the user's normal desktop session (not inside a container or a sandbox without screen access).

Built-in characters: `default` (小码, an original kid coder) and `bubbles` (泡泡, unofficial fan art of Bubbles from The Powerpuff Girls). Pick one with `awesome-pet start --pet bubbles`.

## Control

```bash
awesome-pet stop
awesome-pet status
awesome-pet act front        # face the user
awesome-pet act back         # turn its back to the user
awesome-pet act zoom 1.3     # size, 0.4 to 3
awesome-pet act move 1200 700
awesome-pet act pet NAME     # switch character
awesome-pet act type         # one tap on the keyboard
awesome-pet act click        # one mouse click
```

The user can also drag it, scroll on it to resize, double-click or press F12 to turn it, and right-click for a menu.

On macOS, following the real keyboard and mouse needs the launching app (Terminal, the agent app) to be allowed under System Settings → Privacy & Security → Accessibility / Input Monitoring. Without it the character still shows and `act` still works. Windows needs nothing.

## Make a character from the user's avatar

A character is a folder with `pet.json`, `front.png` and `back.png`. The body pictures have **no arms**; the program draws the arms from the shoulders to the keyboard and the mouse, using the picture's skin tone and outline width.

1. Generate two full-body pictures of the character from the avatar, same style as the avatar:
   - Front: facing the viewer, standing straight, full body, **no arms and no hands at all, the sides of the body are clean outlines**, thick even outlines, flat colors, centered with a wide margin, solid flat pure green background `#00FF00`, no floor, no shadow, no text.
   - Back: the same character seen strictly from behind, same rules, no arms.
   If the model still draws arms, regenerate; stray arms show up as a second pair next to the drawn ones.
2. `awesome-pet pack make NAME --front front.png --back back.png --title "显示名"`
   This keys out the green, finds the shoulders, the outline width, the skin tone and the eyes (for blinking), and installs the pack under `~/.awesome-desktop/pets/NAME`.
3. `awesome-pet preview --pet NAME --out preview.png` and look at the six poses. If an arm starts in the wrong place, edit `shoulders` (pixel positions in the picture) in `pet.json`; `desk` is the height where the desk covers the front body.
4. `awesome-pet start --pet NAME` (or `awesome-pet act pet NAME` if it is already running).

To give a character to someone else: `awesome-pet pack export NAME` writes `NAME.zip`; on the other computer run `awesome-pet pack add NAME.zip`. Label characters drawn after someone else's design as unofficial fan art.
