"""Transliterate Hindi (Devanagari) and Urdu (Arabic) script to
readable romanized Latin text — the way people actually type on
WhatsApp, not academic IAST.

No external dependencies required.
"""

import re


# ── Devanagari ───────────────────────────────────────────────────

_VIRAMA = '\u094D'   # ्  halant – kills inherent 'a'
_NUKTA  = '\u093C'   # ़  dot below – modifies consonant

# Consonant → roman base (without inherent vowel)
_D_CONS = {
    'क': 'k',  'ख': 'kh', 'ग': 'g',  'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh','ज': 'j',  'झ': 'jh', 'ञ': 'ny',
    'ट': 't',  'ठ': 'th', 'ड': 'd',  'ढ': 'dh', 'ण': 'n',
    'त': 't',  'थ': 'th', 'द': 'd',  'ध': 'dh', 'न': 'n',
    'प': 'p',  'फ': 'ph', 'ब': 'b',  'भ': 'bh', 'म': 'm',
    'य': 'y',  'र': 'r',  'ल': 'l',  'व': 'v',
    'श': 'sh', 'ष': 'sh', 'स': 's',  'ह': 'h',
}

# Nukta-modified consonants (क़ ख़ ग़ ज़ फ़ ड़ ढ़)
_D_NUKTA = {
    'क': 'q',  'ख': 'kh', 'ग': 'gh',
    'ज': 'z',  'फ': 'f',
    'ड': 'r',  'ढ': 'rh',
}

# Independent vowels
_D_VOWELS = {
    'अ': 'a',  'आ': 'aa', 'इ': 'i',  'ई': 'ee',
    'उ': 'u',  'ऊ': 'oo', 'ऋ': 'ri',
    'ए': 'e',  'ऐ': 'ai', 'ओ': 'o',  'औ': 'au',
}

# Dependent vowel signs (matras)
_D_MATRAS = {
    'ा': 'aa', 'ि': 'i',  'ी': 'ee',
    'ु': 'u',  'ू': 'oo', 'ृ': 'ri',
    'े': 'e',  'ै': 'ai', 'ो': 'o',  'ौ': 'au',
}


def _romanize_devanagari(text):
    """Transliterate a Devanagari string to Latin script."""

    out = []
    chars = list(text)
    i, n = 0, len(chars)

    while i < n:
        ch = chars[i]

        # ── consonant ──
        if ch in _D_CONS:
            # nukta check  (e.g. ज + ़ = ज़ → 'z')
            if i + 1 < n and chars[i + 1] == _NUKTA:
                base = _D_NUKTA.get(ch, _D_CONS[ch])
                i += 2
            else:
                base = _D_CONS[ch]
                i += 1

            # what follows?
            if i < n and chars[i] == _VIRAMA:
                out.append(base)          # no vowel
                i += 1
            elif i < n and chars[i] in _D_MATRAS:
                out.append(base + _D_MATRAS[chars[i]])
                i += 1
            else:
                out.append(base + 'a')    # inherent 'a'

        # ── independent vowel ──
        elif ch in _D_VOWELS:
            out.append(_D_VOWELS[ch])
            i += 1

        # ── orphan matra (rare) ──
        elif ch in _D_MATRAS:
            out.append(_D_MATRAS[ch])
            i += 1

        # ── anusvara / chandrabindu ──
        elif ch == '\u0902':          # ं
            out.append('n')
            i += 1
        elif ch == '\u0901':          # ँ
            out.append('n')
            i += 1

        # ── visarga ──
        elif ch == '\u0903':          # ः
            out.append('h')
            i += 1

        # ── skip stray virama / nukta ──
        elif ch in (_VIRAMA, _NUKTA):
            i += 1

        # ── Devanagari danda ──
        elif ch in ('\u0964', '\u0965'):
            out.append('.')
            i += 1

        # ── everything else (spaces, punctuation, Latin) ──
        else:
            out.append(ch)
            i += 1

    return ''.join(out)


# ── Urdu / Arabic script ────────────────────────────────────────

_U_CHARS = {
    'ا': 'a', 'آ': 'aa', 'ب': 'b', 'پ': 'p', 'ت': 't', 'ٹ': 't',
    'ث': 's', 'ج': 'j',  'چ': 'ch','ح': 'h', 'خ': 'kh',
    'د': 'd', 'ڈ': 'd',  'ذ': 'z', 'ر': 'r', 'ڑ': 'r', 'ز': 'z',
    'ژ': 'zh','س': 's',  'ش': 'sh','ص': 's', 'ض': 'z',
    'ط': 't', 'ظ': 'z',  'ع': 'a', 'غ': 'gh','ف': 'f', 'ق': 'q',
    'ک': 'k', 'ك': 'k',  'گ': 'g', 'ل': 'l', 'م': 'm', 'ن': 'n',
    'ں': 'n', 'و': 'o',  'ہ': 'h', 'ھ': 'h', 'ء': '',  'ی': 'i',
    'ي': 'i', 'ے': 'e',  'ئ': 'i',
    # short-vowel diacritics
    '\u064E': 'a',   # fatḥa
    '\u064F': 'u',   # ḍamma
    '\u0650': 'i',   # kasra
    '\u0651': '',    # shadda
    '\u0652': '',    # sukūn
    '\u064B': 'an',  # tanwīn fatḥa
    '\u064C': 'un',  # tanwīn ḍamma
    '\u064D': 'in',  # tanwīn kasra
    # zero-width helpers
    '\u200C': '', '\u200D': '', '\u200E': '', '\u200F': '',
}


def _romanize_urdu(text):
    """Best-effort romanization of Urdu (Nastaliq / Arabic) script."""

    out = []
    for ch in text:
        if ch in _U_CHARS:
            out.append(_U_CHARS[ch])
        elif ch.isascii():
            out.append(ch)
        elif 0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFDFF:
            pass                          # unknown Arabic glyph → skip
        else:
            out.append(ch)
    return ''.join(out)


# ── public API ──────────────────────────────────────────────────

_RE_DEVANAGARI = re.compile(r'[\u0900-\u097F]')
_RE_URDU       = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF]')


def romanize(text):
    """Convert Hindi / Urdu text to readable Roman script.

    Handles mixed text (Latin + Devanagari / Urdu) gracefully.
    Returns unchanged text if it is already Latin.
    """
    if not text:
        return text

    # fast path – nothing to do
    if not _RE_DEVANAGARI.search(text) and not _RE_URDU.search(text):
        return text

    # process word-by-word so Latin fragments stay untouched
    parts = text.split(' ')
    result = []

    for part in parts:
        if _RE_DEVANAGARI.search(part):
            result.append(_romanize_devanagari(part))
        elif _RE_URDU.search(part):
            result.append(_romanize_urdu(part))
        else:
            result.append(part)

    return ' '.join(result)
