# Spotify Lyrics Overlay

A frameless, always-on-top lyrics overlay for the Spotify desktop client on Linux.
Track info comes from MPRIS over D-Bus, synced lyrics come from [LRCLIB](https://lrclib.net).

## Features

- **Three-line view** — the line just sung, the line playing now, and the one coming up.
- **Cross-fade** — each line fades out and back in as it changes, no jump cuts.
- **Glass panel** — hand-painted frosted panel with a sheen, rim light and drop shadow.
- **Pause freeze** — on pause the current line stays put, the panel dims and shows a ⏸ mark.
- **Autostart** — one flag installs a `.desktop` entry that launches it on login.
- **Movable and resizable** — drag it anywhere, drag the bottom-right corner to resize.
  Position and size are remembered in `~/.config/spotify-overlay/state.json`.

## Run

```bash
.venv/bin/python app.py
.venv/bin/python app.py --click-through   # ignore the mouse once it is where you want it
```

Drag the panel to move it, drag the marked bottom-right corner to resize it, click the ✕
in the top-right to close it. It never takes keyboard focus, so typing in the window
underneath is not interrupted. Ctrl+C in the terminal works too, and `--quit` closes an
overlay started from the applications grid:

```bash
.venv/bin/python app.py --quit
```

Only one overlay runs at a time: launching a second one hands off to the first and exits,
rather than stacking a duplicate on top of it.

## Autostart on Ubuntu

```bash
.venv/bin/python app.py --install-autostart     # writes ~/.config/autostart/spotify-overlay.desktop
.venv/bin/python app.py --uninstall-autostart
```

The entry records the absolute path of the interpreter that ran it, so install it with the
venv python. It starts 15 seconds after login to give Spotify time to claim its D-Bus name —
though if Spotify is not up yet (or quits later) the overlay just shows
"Waiting for Spotify..." and reconnects on its own.

## Sticky: every workspace, above every window

This needs an **X11 session**, and Qt has no API for it, so the overlay sets the EWMH
hints itself (`_NET_WM_DESKTOP = 0xFFFFFFFF`, plus `sticky,above` through `wmctrl` when
it is installed):

```bash
sudo apt install libxcb-cursor0 wmctrl     # libxcb-cursor0 is required by Qt 6.5+ for xcb
QT_QPA_PLATFORM=xcb .venv/bin/python app.py
```

Under a **native Wayland session the compositor owns window placement and stacking**, and
GNOME exposes no protocol for either — so always-on-top, all-workspaces, and restoring a
saved position simply cannot be honoured there. Dragging and resizing still work, because
those go through the compositor's own move/resize. Run under XWayland as above for the
sticky behaviour.

A window lives on one monitor at a time; "all screens" means it survives monitors coming
and going (a saved position on a monitor that is gone falls back to bottom-centre), not
that it is drawn on several at once.

## Notes

- Real backdrop blur is asked for via `_KDE_NET_WM_BLUR_BEHIND_REGION`, which KWin honours.
  GNOME/Mutter — Ubuntu's default — exposes no blur API to applications, so there the
  frosted look comes entirely from the painted gradient.
- Lyrics are looked up in this order: LRCLIB exact match, LRCLIB search (retried with the
  title stripped of `(From "…")`-style decoration, then with only the first credited
  artist, then title-only), NetEase, and finally the wordless providers, Genius and
  lyrics.ovh. **Real synced lyrics from any provider beat plain lyrics from every
  provider** — plain lyrics have no timestamps, so anything built from them drifts against
  the song. When only those are found the overlay says so and parks on the opening lines
  instead of pretending to follow along.
- Providers list several versions of the same song. The one whose length is closest to the
  track actually playing wins, which is what keeps the lines from running early or late.
- The 16px transparent margin around the panel (it carries the drop shadow) is part of the
  window, so it catches clicks too unless `--click-through` is on.
