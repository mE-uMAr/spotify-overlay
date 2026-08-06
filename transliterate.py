"""Transliterate Hindi (Devanagari), Punjabi (Gurmukhi) and Urdu (Arabic)
script to readable romanized Latin text — the way people actually type on
WhatsApp, not academic IAST.

No external dependencies required.
"""

import re


# ── Devanagari ───────────────────────────────────────────────────

_D_VIRAMA = '्'   # ्  halant – kills inherent 'a'
_D_NUKTA  = '़'   # ़  dot below – modifies consonant

# Consonant → roman base (without inherent vowel)
_D_CONS = {
    'क': 'k',  'ख': 'kh', 'ग': 'g',  'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh','ज': 'j',  'झ': 'jh', 'ञ': 'ny',
    'ट': 't',  'ठ': 'th', 'ड': 'd',  'ढ': 'dh', 'ण': 'n',
    'त': 't',  'थ': 'th', 'द': 'd',  'ध': 'dh', 'न': 'n',
    'प': 'p',  'फ': 'ph', 'ब': 'b',  'भ': 'bh', 'म': 'm',
    'य': 'y',  'र': 'r',  'ल': 'l',  'व': 'v',
    'श': 'sh', 'ष': 'sh', 'स': 's',  'ह': 'h',
    'ळ': 'l',
    # precomposed nukta forms
    'क़': 'q',  'ख़': 'kh', 'ग़': 'gh', 'ज़': 'z',  'फ़': 'f',
    'ड़': 'r',  'ढ़': 'rh',
}

# Nukta-modified consonants (क़ ख़ ग़ ज़ फ़ ड़ ढ़)
_D_NUKTA_MAP = {
    'क': 'q',  'ख': 'kh', 'ग': 'gh',
    'ज': 'z',  'फ': 'f',
    'ड': 'r',  'ढ': 'rh',
}

# Independent vowels. Hindi's long/short pairs (इ/ई, उ/ऊ) both land on the
# same letter because that is how the language is actually typed in Latin:
# "koi", never "koee".
_D_VOWELS = {
    'अ': 'a',  'आ': 'aa', 'इ': 'i',  'ई': 'i',
    'उ': 'u',  'ऊ': 'u',  'ऋ': 'ri',
    'ए': 'e',  'ऐ': 'ai', 'ओ': 'o',  'औ': 'au',
    'ऑ': 'o',  'ऍ': 'e',
}

# Dependent vowel signs (matras)
_D_MATRAS = {
    'ा': 'aa', 'ि': 'i',  'ी': 'i',
    'ु': 'u',  'ू': 'u',  'ृ': 'ri',
    'े': 'e',  'ै': 'ai', 'ो': 'o',  'ौ': 'au',
    'ॉ': 'o',  'ॅ': 'e',
}

_D_MARKS = ('ं', 'ँ', 'ः')   # anusvara, chandrabindu, visarga


# ── Gurmukhi (Punjabi) ───────────────────────────────────────────
#
# Structurally the same kind of script as Devanagari — consonants carry
# an unwritten 'a', matras replace it, a halant kills it — so it runs
# through exactly the same machinery with its own tables. The one thing
# Devanagari has no equivalent for is the addak, which doubles the
# consonant that follows it.

_G_VIRAMA = '੍'
_G_NUKTA  = '਼'
_G_ADDAK  = 'ੱ'

_G_CONS = {
    'ਕ': 'k',  'ਖ': 'kh', 'ਗ': 'g',  'ਘ': 'gh', 'ਙ': 'ng',
    'ਚ': 'ch', 'ਛ': 'chh','ਜ': 'j',  'ਝ': 'jh', 'ਞ': 'ny',
    'ਟ': 't',  'ਠ': 'th', 'ਡ': 'd',  'ਢ': 'dh', 'ਣ': 'n',
    'ਤ': 't',  'ਥ': 'th', 'ਦ': 'd',  'ਧ': 'dh', 'ਨ': 'n',
    'ਪ': 'p',  'ਫ': 'ph', 'ਬ': 'b',  'ਭ': 'bh', 'ਮ': 'm',
    'ਯ': 'y',  'ਰ': 'r',  'ਲ': 'l',  'ਵ': 'v',  'ੜ': 'r',
    'ਸ': 's',  'ਹ': 'h',
    # precomposed nukta forms
    'ਸ਼': 'sh', 'ਖ਼': 'kh', 'ਗ਼': 'gh', 'ਜ਼': 'z',  'ਫ਼': 'f',
    'ਲ਼': 'l',
    # bare vowel carriers: no sound of their own, they just hold a matra
    'ੳ': '',   'ੲ': '',
}

_G_NUKTA_MAP = {
    'ਸ': 'sh', 'ਖ': 'kh', 'ਗ': 'gh',
    'ਜ': 'z',  'ਫ': 'f',  'ਲ': 'l',
    'ਕ': 'q',
}

_G_VOWELS = {
    'ਅ': 'a',  'ਆ': 'aa', 'ਇ': 'i',  'ਈ': 'i',
    'ਉ': 'u',  'ਊ': 'u',
    'ਏ': 'e',  'ਐ': 'ai', 'ਓ': 'o',  'ਔ': 'au',
}

_G_MATRAS = {
    'ਾ': 'aa', 'ਿ': 'i',  'ੀ': 'i',
    'ੁ': 'u',  'ੂ': 'u',
    'ੇ': 'e',  'ੈ': 'ai', 'ੋ': 'o',  'ੌ': 'au',
}

_G_MARKS = ('ਂ', 'ੰ', 'ਃ')   # bindi, tippi, visarga


_DANDA = ('।', '॥')

_VISARGAS = ('ः', 'ਃ')

# every consonant carries an unwritten 'a' unless something replaces it
_INHERENT = 'a'


class _Script:
    """The per-script tables the shared parser reads."""

    def __init__(
        self,
        cons,
        nukta_map,
        vowels,
        matras,
        marks,
        virama,
        nukta,
        addak=None,
    ):

        self.cons = cons
        self.nukta_map = nukta_map
        self.vowels = vowels
        self.matras = matras
        self.marks = marks
        self.virama = virama
        self.nukta = nukta

        # Gurmukhi only
        self.addak = addak


DEVANAGARI = _Script(
    _D_CONS, _D_NUKTA_MAP, _D_VOWELS, _D_MATRAS, _D_MARKS,
    _D_VIRAMA, _D_NUKTA,
)

GURMUKHI = _Script(
    _G_CONS, _G_NUKTA_MAP, _G_VOWELS, _G_MATRAS, _G_MARKS,
    _G_VIRAMA, _G_NUKTA, addak=_G_ADDAK,
)


class _Unit:
    """One written syllable: a consonant cluster and the vowel on it.

    Schwa deletion is a decision about a whole syllable and about the
    syllables on either side of it, so a word is modelled as a list of
    these before any of it is turned back into letters.
    """

    __slots__ = ("cons", "vowel", "inherent", "literal")

    def __init__(self, cons="", vowel="", inherent=False, literal=None):

        self.cons = cons
        self.vowel = vowel

        # True only while the vowel is still the unwritten 'a' — that is
        # the one vowel allowed to disappear
        self.inherent = inherent

        # punctuation and anything else passed straight through, which
        # doubles as a word boundary for the rules below
        self.literal = literal

    def text(self):

        if self.literal is not None:
            return self.literal

        return self.cons + self.vowel


def _double(cons):
    """What the Gurmukhi addak does to the consonant after it.

    Only single letters take the doubling: ਚੁੱਪ is "chupp" and ਇੱਕੋ is
    "ikko", but doubling a digraph would turn ਪਿੱਛੇ into "picchhe" when
    the word everybody writes is "pichhe".
    """

    if len(cons) != 1:
        return cons

    return cons * 2


def _parse(text, script):
    """An Indic word into syllable units."""

    units = []

    chars = list(text)
    i, n = 0, len(chars)

    pending_double = False

    while i < n:

        ch = chars[i]

        if script.addak is not None and ch == script.addak:

            pending_double = True
            i += 1
            continue

        if ch in script.cons:

            # nukta check  (e.g. ज + ़ = ज़ → 'z')
            if i + 1 < n and chars[i + 1] == script.nukta:
                cons = script.nukta_map.get(ch, script.cons[ch])
                i += 2
            else:
                cons = script.cons[ch]
                i += 1

            if pending_double:

                cons = _double(cons)
                pending_double = False

            if i < n and chars[i] == script.virama:
                # bare consonant, joined onto whatever follows
                units.append(_Unit(cons, ""))
                i += 1

            elif i < n and chars[i] in script.matras:
                units.append(_Unit(cons, script.matras[chars[i]]))
                i += 1

            else:
                units.append(_Unit(cons, _INHERENT, inherent=True))

        elif ch in script.vowels:

            units.append(_Unit("", script.vowels[ch]))
            i += 1

        elif ch in script.matras:

            # orphan matra, no consonant to hang off
            units.append(_Unit("", script.matras[ch]))
            i += 1

        elif ch in (script.virama, script.nukta):

            i += 1

        elif ch in _DANDA:

            units.append(_Unit(literal="."))
            i += 1

        elif ch in script.marks:

            # leading mark with nothing to attach to
            i += 1

        else:

            units.append(_Unit(literal=ch))
            i += 1

        # a nasal or visarga belongs to the syllable just built
        while i < n and chars[i] in script.marks:

            if units:
                _add_mark(units[-1], chars[i])

            i += 1

    return units


def _add_mark(unit, mark):

    if unit.literal is not None:
        return

    if mark in _VISARGAS:

        unit.vowel += "h"

        return

    # में is written "mein", not "men" — the nasal after a plain 'e' is
    # heard as a glide into it
    if unit.vowel == "e":
        unit.vowel = "ein"

    else:
        unit.vowel += "n"

    # a nasalised vowel is pronounced, so it can no longer be dropped
    unit.inherent = False


def _spoken(units):

    return [
        index
        for index, unit in enumerate(units)
        if unit.literal is None
    ]


def _delete_schwa(units):
    """Drop the inherent 'a' wherever the language does not pronounce it.

    This is the whole difference between "ishqa men dila" and "ishq mein
    dil". Two rules cover almost everything:

    - the 'a' ending a word is silent, unless the word is one syllable
      and would be left with no vowel at all ("na" stays "na");
    - an 'a' between two pronounced syllables is silent too, which is why
      मुझको is "mujhko" and not "mujhako".

    The medial pass runs right to left and only deletes next to syllables
    that still have a vowel, so it never strips two in a row and leaves
    an unpronounceable cluster behind.
    """

    spoken = _spoken(units)

    if not spoken:
        return units

    # ── final schwa ──
    last = units[spoken[-1]]

    if last.inherent and len(spoken) > 1:

        last.vowel = ""
        last.inherent = False

    # ── medial schwa ──
    for position in range(len(spoken) - 2, 0, -1):

        unit = units[spoken[position]]

        if not unit.inherent:
            continue

        before = units[spoken[position - 1]]
        after = units[spoken[position + 1]]

        if before.vowel and after.vowel:

            unit.vowel = ""
            unit.inherent = False

    return units


# a bare vowel straight after one of these grows a semivowel in speech
_GLIDE_AFTER = ("a", "aa", "i")


def _glide(units):
    """आए is "aaye" and ਦੁਨੀਆ is "duniya", not "aae" and "duniaa"."""

    spoken = _spoken(units)

    for position in range(1, len(spoken)):

        unit = units[spoken[position]]
        before = units[spoken[position - 1]]

        if unit.cons or not unit.vowel:
            continue

        if before.vowel in _GLIDE_AFTER and unit.vowel[0] in "aeiou":

            unit.cons = "y"

    return units


def _shorten_final_a(units):
    """तेरा is "tera", not "teraa".

    A long 'aa' closing a word is written with one letter — tera, gaya,
    kya, itna — while one in the middle keeps both, which is what stops
    रात from turning into "rat".
    """

    spoken = _spoken(units)

    if not spoken:
        return units

    last = units[spoken[-1]]

    if last.vowel.startswith("aa"):

        last.vowel = "a" + last.vowel[2:]

    return units


def _romanize_indic(text, script):

    units = _parse(text, script)

    units = _shorten_final_a(_glide(_delete_schwa(units)))

    return "".join(unit.text() for unit in units)


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
    'َ': 'a',   # fatḥa
    'ُ': 'u',   # ḍamma
    'ِ': 'i',   # kasra
    'ّ': '',    # shadda
    'ْ': '',    # sukūn
    'ً': 'an',  # tanwīn fatḥa
    'ٌ': 'un',  # tanwīn ḍamma
    'ٍ': 'in',  # tanwīn kasra
    # zero-width helpers
    '‌': '', '‍': '', '‎': '', '‏': '',
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

_RE_DEVANAGARI = re.compile(r'[ऀ-ॿ]')
_RE_GURMUKHI   = re.compile(r'[਀-੿]')
_RE_URDU       = re.compile(r'[؀-ۿﭐ-﷿]')

_RE_ANY = re.compile(
    r'[ऀ-ॿ਀-੿؀-ۿﭐ-﷿]'
)


def romanize(text):
    """Convert Hindi / Punjabi / Urdu text to readable Roman script.

    Handles mixed text (Latin + Indic / Urdu) gracefully.
    Returns unchanged text if it is already Latin.
    """
    if not text:
        return text

    # fast path – nothing to do
    if not _RE_ANY.search(text):
        return text

    # process word-by-word so Latin fragments stay untouched
    parts = text.split(' ')
    result = []

    for part in parts:
        if _RE_DEVANAGARI.search(part):
            result.append(_romanize_indic(part, DEVANAGARI))
        elif _RE_GURMUKHI.search(part):
            result.append(_romanize_indic(part, GURMUKHI))
        elif _RE_URDU.search(part):
            result.append(_romanize_urdu(part))
        else:
            result.append(part)

    return ' '.join(result)
