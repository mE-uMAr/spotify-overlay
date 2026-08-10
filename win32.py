"""The Windows half of the overlay's window tricks.
Linux gets its always-on-top and its blur by shelling out to xprop and
wmctrl; neither exists here, so the same two jobs go straight at user32
through ctypes. Everything is best effort — the painted glass panel in
overlay.py stands on its own if any of it is refused.

Imported only from the Windows branches in overlay.py, but importing it
anywhere else is harmless: the DLLs are looked up lazily.
"""

import ctypes

from ctypes import wintypes


GWL_EXSTYLE = -20

WS_EX_TOOLWINDOW = 0x00000080   # keeps it out of the taskbar and Alt+Tab
WS_EX_NOACTIVATE = 0x08000000   # clicking it never steals focus
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


WCA_ACCENT_POLICY = 19

ACCENT_ENABLE_BLURBEHIND = 3


class AccentPolicy(ctypes.Structure):

    _fields_ = [
        ("accent_state", ctypes.c_int),
        ("accent_flags", ctypes.c_int),
        ("gradient_colour", ctypes.c_uint),
        ("animation_id", ctypes.c_int),
    ]


class CompositionAttributeData(ctypes.Structure):

    _fields_ = [
        ("attribute", ctypes.c_int),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_size_t),
    ]


_user32 = None


def user32():
    """user32 with argument types declared.

    ctypes defaults every argument to a C int, which quietly truncates a
    64-bit window handle into garbage, so the signatures below are not
    optional.
    """

    global _user32

    if _user32 is not None:
        return _user32

    library = ctypes.WinDLL("user32", use_last_error=True)

    # GetWindowLongPtrW only exists on 64-bit Windows; on 32-bit the
    # pointer-sized call *is* the plain one
    library.get_style = getattr(
        library,
        "GetWindowLongPtrW",
        library.GetWindowLongW,
    )

    library.set_style = getattr(
        library,
        "SetWindowLongPtrW",
        library.SetWindowLongW,
    )

    library.get_style.argtypes = (wintypes.HWND, ctypes.c_int)
    library.get_style.restype = ctypes.c_ssize_t

    library.set_style.argtypes = (
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_ssize_t,
    )
    library.set_style.restype = ctypes.c_ssize_t

    library.SetWindowPos.argtypes = (
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    )
    library.SetWindowPos.restype = wintypes.BOOL

    _user32 = library

    return _user32


def keep_above_everything(handle):
    """Pin the overlay above every other window.

    Qt's WindowStaysOnTopHint already asks for this, but the flag is lost
    the moment another application makes itself topmost, so it is
    re-asserted here through SetWindowPos. WS_EX_TOOLWINDOW additionally
    keeps the overlay out of the taskbar and out of Alt+Tab — which
    Qt::Tool would also do, at the price of Qt hiding the window every
    time the application is deactivated.

    Windows exposes no public API for "on every virtual desktop", so
    unlike the X11 path the overlay stays on the desktop it opened on.
    """

    try:

        library = user32()

        window = wintypes.HWND(handle)

        library.set_style(
            window,
            GWL_EXSTYLE,
            library.get_style(window, GWL_EXSTYLE)
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
            | WS_EX_TOPMOST,
        )

        return bool(
            library.SetWindowPos(
                window,
                wintypes.HWND(HWND_TOPMOST),
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
            )
        )

    except Exception as error:

        print("Could not pin the overlay on top:", error)

        return False


def enable_blur_behind(handle):
    """Ask the compositor to blur what is behind the window.

    SetWindowCompositionAttribute is what the shell itself uses and what
    every acrylic effect on Windows goes through, but Microsoft never
    documented it, so it is resolved by name and skipped when missing
    rather than assumed. The KDE blur hint on Linux is the counterpart.
    """

    try:

        library = user32()

        composition = getattr(
            library,
            "SetWindowCompositionAttribute",
            None,
        )

        if composition is None:
            return False

        composition.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(CompositionAttributeData),
        )
        composition.restype = wintypes.BOOL

        policy = AccentPolicy(ACCENT_ENABLE_BLURBEHIND, 0, 0, 0)

        data = CompositionAttributeData(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            ctypes.sizeof(policy),
        )

        return bool(
            composition(
                wintypes.HWND(handle),
                ctypes.byref(data),
            )
        )

    except Exception:

        # blur is decoration; the painted gradient carries the look
        return False
