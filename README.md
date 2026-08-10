# Spotify Lyrics Overlay

A frameless, always-on-top lyrics overlay for the Spotify desktop client, on
**Linux and Windows**. Synced lyrics come from [LRCLIB](https://lrclib.net), with
NetEase, Genius and lyrics.ovh behind it as fallbacks.

Hindi, Punjabi and Urdu lyrics are romanized on the way in, so
`ਚੁੱਪ ਕਰ ਲੰਘ ਜਾਵੇ` reaches the screen as `chupp kar langh jaave` — readable whether
or not you read the script.

<!-- a screenshot or short gif of the overlay over a desktop goes well here -->

## Features

- **Three-line view** — the line just sung, the line playing now, and the one coming up.
- **Cross-fade** — each line fades out and back in as it changes, no jump cuts.
- **Glass panel** — hand-painted frosted panel with a sheen, rim light and drop shadow.
- **Pause freeze** — on pause the current line stays put, the panel dims and shows a ⏸ mark.
- **Romanized Indic lyrics** — Devanagari, Gurmukhi and Nastaliq become Latin letters.
- **Never steals focus** — click or drag it and whatever you were typing underneath keeps
  the keyboard.
- **Movable and resizable** — drag it anywhere, drag the bottom-right corner to resize.
  Position and size are remembered between runs.
- **Autostart** — one flag registers it in the applications menu and runs it on login.

## Install

Grab a prebuilt binary from the [releases page](../../releases) — `SpotifyLyricsOverlay.exe`
for Windows, `spotify-overlay` for Linux. No account needed. Every push to `main` also
publishes a [rolling build](../../releases/tag/latest) if you want the newest changes
before they are tagged.

On Linux, mark it executable first:

```bash
chmod +x spotify-overlay
./spotify-overlay
```

Or run from source:

```bash
git clone https://github.com/me-umar/spotify-overlay
cd spotify-overlay

python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
```

`requirements.txt` carries both backends behind platform markers, so pip installs only
the one your OS needs.

### Linux also needs the Qt xcb libraries

```bash
sudo apt install libxcb-cursor0 wmctrl     # libxcb-cursor0 is required by Qt 6.5+ for xcb
```

`wmctrl` is optional; without it the overlay still floats on top, it just cannot ask to
appear on every workspace. If you cannot install packages, the same libraries can be
unpacked into `vendor/` and the launcher will find them there.

## Run

```bash
.venv/bin/python app.py
.venv/bin/python app.py --click-through   # ignore the mouse once it is where you want it
```

It prints which OS it detected and which backend it picked, then waits for Spotify.

Drag the panel to move it, drag the marked bottom-right corner to resize it, click the ✕
in the top-right to close it. It never takes keyboard focus, so typing in the window
underneath is not interrupted. Ctrl+C in the terminal works too, and `--quit` closes an
overlay started from the applications menu:

```bash
.venv/bin/python app.py --quit
```

Only one overlay runs at a time: launching a second one hands off to the first and exits,
rather than stacking a duplicate on top of it.

## Autostart

```bash
python app.py --install             # applications menu + run on login
python app.py --install app         # just the menu entry
python app.py --install autostart   # just the login entry
python app.py --uninstall
```

On Linux this writes `.desktop` files under `~/.local/share/applications` and
`~/.config/autostart`; the login entry starts 15 seconds late so Spotify claims its
D-Bus name first. On Windows it writes shortcuts into the Start Menu and the Startup
folder, built through PowerShell's `WScript.Shell` so there is no `pywin32` dependency
for those few lines.

Either way the launcher records the absolute path of the interpreter that ran it, so
install it with the same Python you run it with. If Spotify is not up yet — or quits
later — the overlay just shows "Waiting for Spotify..." and reconnects on its own.

## How it reads the current track

| | Linux | Windows |
|---|---|---|
| Source | MPRIS over D-Bus | `GlobalSystemMediaTransportControlsSession` |
| Backend | `spotify_mpris.py` | `spotify_winrt.py` |
| Always on top | `_NET_WM_DESKTOP` + `wmctrl` | `WS_EX_TOPMOST` via `user32` |
| On every workspace | yes, under X11 | no — Windows exposes no API for it |
| Backdrop blur | `_KDE_NET_WM_BLUR_BEHIND_REGION` (KWin) | `SetWindowCompositionAttribute` |
| Config lives in | `~/.config/spotify-overlay/` | `%APPDATA%\spotify-overlay\` |

Both backends answer the same four coroutines and both report status in MPRIS's
`Playing`/`Paused`/`Stopped` vocabulary, so nothing above them knows which one it got.
`platform_support.py` decides once, at startup, and everything platform-specific branches
on it rather than testing `sys.platform` again.

One Windows quirk is worth knowing: the media session only publishes a new playback
position when something *happens* — a seek, a pause, a track change — so between those the
reported position is a stale snapshot. `spotify_winrt.py` adds the wall-clock time since
that snapshot, which keeps the lyrics moving in step with the music.

## Sticky: every workspace, above every window (Linux)

This needs an **X11 session**, and Qt has no API for it, so the overlay sets the EWMH hints
itself (`_NET_WM_DESKTOP = 0xFFFFFFFF`, plus `sticky,above` through `wmctrl` when it is
installed). `app.py` re-execs under `QT_QPA_PLATFORM=xcb` automatically when a display is
present.

Under a **native Wayland session the compositor owns window placement and stacking**, and
GNOME exposes no protocol for either — so always-on-top, all-workspaces, and restoring a
saved position simply cannot be honoured there. Dragging and resizing still work, because
those go through the compositor's own move/resize. Run under XWayland for the sticky
behaviour.

A window lives on one monitor at a time; "all screens" means it survives monitors coming
and going (a saved position on a monitor that is gone falls back to bottom-centre), not
that it is drawn on several at once.

## Building a binary

```bash
pip install pyinstaller
pyinstaller spotify-overlay.spec
```

One spec covers both platforms — it excludes the other OS's backend and picks the right
name, icon and console setting. The GitHub Actions workflows in `.github/workflows/` run
exactly that on `windows-latest` and `ubuntu-22.04` for every push and pull request. Pushing
a `v*` tag attaches the binaries to that release; a push to `main` refreshes the rolling
`latest` prerelease instead. Pull request builds stay as run artifacts, which are only
reachable by signed-in users with read access and expire after 90 days — that is a GitHub
limitation, so anything meant for users goes to a release.

## Notes

- Real backdrop blur is asked for via `_KDE_NET_WM_BLUR_BEHIND_REGION`, which KWin honours.
  GNOME/Mutter — Ubuntu's default — exposes no blur API to applications, so there the
  frosted look comes entirely from the painted gradient. On Windows the equivalent goes
  through the undocumented `SetWindowCompositionAttribute`, and is skipped if it is absent.
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
- The romanizer is hand-written and dependency-free (`transliterate.py`). It models
  syllables rather than characters so it can do schwa deletion — the rule that turns
  `इश्क़ में दिल` into `ishq mein dil` rather than `ishqa men dila`. Gurmukhi reuses the
  Devanagari parser wholesale, with its own tables and the addak on top.

## Contributing

Issues and pull requests are welcome. Useful things to know:

- No formatter is enforced; match the surrounding style, which runs to short functions and
  comments that explain *why* rather than *what*.
- Both build workflows run on every pull request, so a change that breaks either platform
  shows up before it lands.
- Adding a script to the romanizer means a table plus one branch in `romanize()`.

## License

[MIT](LICENSE) — do what you like with it, just keep the copyright notice.

The `.so` files under `vendor/` are unmodified Debian builds of libxcb, libxkbcommon and
friends, redistributed under their own (MIT-style) licenses; their copyright files ship
alongside them in `vendor/usr/share/doc/`.
