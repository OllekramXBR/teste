"""Search and fetch charts from Cifra Club.

Cifra Club is a Brazilian chord/lyric site. Searching goes through its Solr
autocomplete endpoint, which returns the song, artist, and the two slugs that
identify its page. Fetching the chart is the subtle part: the ``<pre>`` the
server renders contains only a preview of the chart, and the full chart ships
inside the React Server Component payload — a stream of ``push([1,"..."])``
segments whose decoded text is rows of ``id:type data``. The song's data lives
in a ``songData`` object whose ``content`` field is a deferral reference
(``"$77"``) to the row that holds the whole chart as a tree of
``["$", tag, props, ...children]`` nodes. We decode that tree instead of the
HTML.

The module only ever talks to Cifra Club with URLs it built itself from the
slugs its own search returned, which is what keeps an "import this chart" call
from becoming a way to make the server fetch an arbitrary URL.

Both the search and the page declare ``charset=utf-8`` while actually sending
latin-1 bytes, so decoding falls back to latin-1 when the declared charset
fails.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SEARCH_URL = "https://solr.sscdn.co/cc/c7/"
PAGE_URL = "https://www.cifraclub.com.br/{dns}/{url}/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
# The chart page is a Next.js bundle of roughly half a megabyte; the ceiling
# is generous but still stops a wedged response from being held in memory.
MAX_PAGE_BYTES = 8 * 1024 * 1024

_SEARCH_RESULT_PATTERN = re.compile(r'"tipo":"(2|3|4)"')
_OG_TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
_OG_IMAGE_PATTERN = re.compile(r'<meta property="og:image" content="([^"]*)"')
_TOM_KEY_PATTERN = re.compile(r'data-anchor="--chord-tone"[^>]*>([^<]*)<')
_PUSH_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)

# Brazilian chord suffix -> the app's internal quality name. The site writes
# C7M, Cm, Bm7(b5), C°, C+; the analysis writes maj7, m, m7b5, dim, aug.
_BR_QUALITY: dict[str, str] = {
    "": "",
    "m": "m",
    "7": "7",
    "m7": "m7",
    "7M": "maj7",
    "7+": "maj7",
    "maj7": "maj7",
    "°": "dim",
    "°7": "dim7",
    "dim": "dim",
    "dim7": "dim7",
    "+": "aug",
    "aug": "aug",
    "sus": "sus4",
    "sus4": "sus4",
    "4": "sus4",
    "sus2": "sus2",
    "2": "sus2",
    "6": "6",
    "m6": "m6",
    "m7(b5)": "m7b5",
    "m7b5": "m7b5",
    "ø": "m7b5",
    "5": "",
    "9": "7",
    "7/9": "7",
    "7M/9": "maj7",
    "add9": "",
    "add2": "",
    "add4": "sus4",
    "6/9": "6",
    "maj9": "maj7",
    "m9": "m7",
    "11": "7",
    "13": "7",
}

_ROOT_PATTERN = re.compile(r"^([A-G][#b]?)(.*)$")
# Longest suffixes first so "m7(b5)" beats "m7".
_QUALITY_KEYS = sorted(_BR_QUALITY, key=len, reverse=True)


class CifraclubError(RuntimeError):
    """The site was unreachable, or returned something unreadable."""


@dataclass
class SearchResult:
    """One song from the autocomplete search, enough to open its page."""

    id: int
    title: str
    artist: str
    dns: str
    url: str
    album: str = ""
    image: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "dns": self.dns,
            "url": self.url,
            "album": self.album,
            "image": self.image,
        }


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read(MAX_PAGE_BYTES + 1)
            if len(raw) > MAX_PAGE_BYTES:
                raise CifraclubError("the page is larger than the limit")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                return raw.decode(charset)
            except UnicodeDecodeError:
                # The site declares utf-8 and sends latin-1. Strict decoding
                # fails on the first accent; latin-1 never fails.
                return raw.decode("latin-1")
    except urllib.error.HTTPError:
        # Not wrapped: 404 means "nothing at that address" and the caller
        # decides what that means; every other status is an error it re-raises.
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise CifraclubError(f"Cifra Club is unreachable: {error}") from error


def search(query: str, limit: int = 12) -> list[SearchResult]:
    """The songs on Cifra Club that match the query.

    The autocomplete index also returns artists, setlists and videos; only
    entries typed as songs (tipo 2/3/4) are kept, deduplicated by song id, and
    cut to the limit.
    """
    q = query.strip()
    if not q:
        return []
    url = SEARCH_URL + "?q=" + urllib.parse.quote(q)
    payload = _fetch(url)
    try:
        data = json.loads(payload)
        docs = data["response"]["docs"]
    except (ValueError, KeyError, TypeError) as error:
        raise CifraclubError("Cifra Club returned an unreadable search result") from error

    results: list[SearchResult] = []
    seen: set[int] = set()
    for doc in docs:
        tipo = str(doc.get("tipo", ""))
        if tipo not in ("2", "3", "4"):
            continue
        song_id = doc.get("id_song")
        if not song_id or song_id in seen:
            continue
        dns, slug = doc.get("dns", ""), doc.get("url", "")
        if not dns or not slug:
            continue
        seen.add(song_id)
        results.append(
            SearchResult(
                id=song_id,
                title=doc.get("txt") or "",
                artist=doc.get("art") or "",
                dns=dns,
                url=slug,
                album=doc.get("album_name") or "",
                image=doc.get("imgm") or doc.get("img") or "",
            )
        )
        if len(results) >= limit:
            break
    return results


def _decode_flight(page: str) -> str:
    """Join the RSC push segments into one flight string."""
    segments: list[str] = []
    for match in _PUSH_PATTERN.finditer(page):
        try:
            segments.append(json.loads('"' + match.group(1) + '"'))
        except ValueError:
            continue
    return "".join(segments)


def _parse_flight(flight: str) -> dict[str, str]:
    """The flight stream as ``{row_id: typed data}``.

    Rows are ``\n<id>:<payload>``. Most payloads are JSON values, whose extent
    a JSON decoder reports; a text row is ``T<hex length>,<raw text>`` whose
    raw text may contain real newlines, so its extent comes from the declared
    length rather than the line break. A continuation of an already-seen text
    row is appended to it.
    """
    rows: dict[str, str] = {}
    decoder = json.JSONDecoder()
    index = 0
    length = len(flight)
    while index < length:
        if flight[index] == "\n":
            index += 1
            continue
        end = flight.find(":", index)
        if end < 0:
            break
        row_id = flight[index:end]
        if not row_id or any(char not in "0123456789abcdef" for char in row_id):
            index += 1
            continue
        index = end + 1
        if index >= length:
            break
        row_type = flight[index]
        if row_type == "T":
            header_end = flight.find(",", index)
            if header_end < 0:
                break
            # The declared length is in bytes, and the chart text carries
            # accents, so byte lengths and character counts diverge.
            text_length = int(flight[index + 1 : header_end], 16)
            text_start = header_end + 1
            text_bytes = flight[text_start:].encode("utf-8")[:text_length]
            text = text_bytes.decode("utf-8", errors="replace")
            if row_id in rows:
                rows[row_id] += text
            else:
                rows[row_id] = "T" + text
            index = text_start + len(text)
            continue
        try:
            _, extent = decoder.raw_decode(flight, index)
        except ValueError:
            # Rows such as I[...] and HL[...] carry a type prefix before the
            # JSON value; try past one, two or three prefix characters.
            for skip in (1, 2, 3):
                try:
                    _, extent = decoder.raw_decode(flight, index + skip)
                    break
                except ValueError:
                    continue
            else:
                extent = length
        rows[row_id] = flight[index:extent]
        index = extent
    return rows


def _song_data(flight: str) -> tuple[dict, dict]:
    """The ``songData`` object and the rows of the flight stream.

    The object is embedded in a row of the stream as ``{"songData": {...}}``;
    we locate it and decode the JSON object with a raw decoder so it does not
    need to start at a row boundary.
    """
    rows = _parse_flight(flight)
    decoder = json.JSONDecoder()
    for data in rows.values():
        offset = 0
        while True:
            index = data.find('"songData"', offset)
            if index < 0:
                break
            start = index - 1
            if start < 0 or data[start] != "{":
                offset = index + 1
                continue
            try:
                obj, _ = decoder.raw_decode(data, start)
            except ValueError:
                offset = index + 1
                continue
            song_data = obj.get("songData")
            if isinstance(song_data, dict) and str(song_data.get("content", "")).startswith("$"):
                return song_data, rows
            offset = index + 1
    raise CifraclubError("this page has no readable chart")


def _content_of(row_data: str) -> str | list:
    """The value of a content row: either the raw chart text (``T`` rows) or
    the element tree (``I[...]`` and plain JSON rows)."""
    payload = row_data
    if payload.startswith("T"):
        return payload[1:]
    for skip in (0, 1, 2, 3):
        try:
            value = json.loads(payload[skip:])
            break
        except ValueError:
            continue
    else:
        raise CifraclubError("the chart data could not be read from the page")
    # A module row is [module_id, element, ...]; an element row is the tree.
    if isinstance(value, list) and value and isinstance(value[0], int):
        value = value[1]
    return value


def _walk_inline(children: list, out: list) -> None:
    """Flatten a node's children into ("t", text) / ("c", chord) events."""
    for child in children:
        if isinstance(child, str):
            out.append(("t", child))
        elif isinstance(child, list) and child and child[0] == "$" and isinstance(child[1], str):
            tag = child[1]
            props = child[2] if len(child) > 2 else {}
            kids = child[3:]
            if isinstance(props, str):
                kids = [props] + kids
                props = {}
            if tag == "b":
                name = props.get("data-chord-name", "")
                if name:
                    out.append(("c", name))
            else:
                _walk_inline(kids, out)


def _build_lines(children: list) -> list[dict]:
    """The chart lines out of a ``<pre>`` element's children.

    Each ``kvMV`` div is one verse line (text plus chords with the character
    column each chord sits over); a ``tabs`` div inside it becomes one tab
    block, its chord names kept inline in the tab text exactly as written.
    """
    lines: list[dict] = []
    for child in children:
        if not (isinstance(child, list) and child and child[0] == "$" and isinstance(child[1], str)):
            continue
        tag = child[1]
        props = child[2] if len(child) > 2 else {}
        kids = child[3:]
        if isinstance(props, str):
            kids = [props] + kids
            props = {}
        cls = props.get("className") or ""
        if tag != "div" or "kvMV" not in cls:
            lines.extend(_build_lines(kids))
            continue

        text = ""
        chords: list[dict] = []
        for kid in kids:
            if isinstance(kid, str):
                text += kid
                continue
            if not (isinstance(kid, list) and kid and kid[0] == "$" and isinstance(kid[1], str)):
                continue
            ktag = kid[1]
            kprops = kid[2] if len(kid) > 2 else {}
            kkids = kid[3:]
            if isinstance(kprops, str):
                kkids = [kprops] + kkids
                kprops = {}
            kcls = kprops.get("className") or ""
            if ktag == "b":
                name = kprops.get("data-chord-name", "")
                if name:
                    chords.append({"name": name, "col": len(text)})
            elif ktag == "div" and "tabs" in kcls:
                for span in kkids:
                    if not (isinstance(span, list) and span and span[0] == "$" and span[1] == "span"):
                        continue
                    sprops = span[2] if len(span) > 2 else {}
                    skids = span[3:]
                    if isinstance(sprops, str):
                        skids = [sprops] + skids
                    events: list = []
                    _walk_inline(skids, events)
                    inline = "".join(name if kind == "c" else piece for kind, piece in events)
                    lines.append({"kind": "tab", "text": inline})
            else:
                events: list = []
                _walk_inline([kid], events)
                for kind, piece in events:
                    if kind == "t":
                        text += piece
                    else:
                        chords.append({"name": piece, "col": len(text)})
        if text.strip() or chords:
            lines.append({"kind": "verse", "text": text.rstrip(), "chords": chords})
    return lines


def _normalize_quality(suffix: str) -> str | None:
    """A Brazilian chord suffix into the internal quality name."""
    if suffix.startswith("m7(") and "b5" in suffix:
        return "m7b5"
    cleaned = re.sub(r"\([^)]*\)", "", suffix)
    for key in _QUALITY_KEYS:
        if cleaned == key:
            return _BR_QUALITY[key]
    return None


def normalize_label(label: str) -> dict | None:
    """Parse a Brazilian chord label into ``{"root", "quality", "raw"}``.

    ``root`` is the app's pitch-class number, ``quality`` the internal quality
    name, and ``raw`` the label as written. Returns None when the label is not
    a chord (a section name like ``[Intro]`` or a notation the site invents).
    """
    from .analysis import theory

    label = label.strip()
    match = _ROOT_PATTERN.match(label)
    if not match:
        return None
    root_name, suffix = match.group(1), match.group(2).strip()
    root = theory.NAME_TO_PC.get(root_name.lower())
    if root is None:
        return None
    quality = _normalize_quality(suffix)
    if quality is None:
        return None
    return {"root": root, "quality": quality, "raw": label}


_CHORD_TAG_PATTERN = re.compile(r"<b[^>]*>(.*?)</b>")


def _scan_line(raw_line: str) -> tuple[str, list[dict]]:
    """``"  <b>C</b>   <b>Am7</b>"`` -> ``("  C   Am7", [C@col, Am7@col])``.

    Chord names stay in the text (the site's pre already spaces them into
    place), and the column is where each name ends up in that text.
    """
    text: list[str] = []
    chords: list[dict] = []
    cursor = 0
    for match in _CHORD_TAG_PATTERN.finditer(raw_line):
        text.append(raw_line[cursor : match.start()])
        name = match.group(1)
        chords.append({"name": name, "col": len("".join(text))})
        text.append(name)
        cursor = match.end()
    text.append(raw_line[cursor:])
    return "".join(text), chords


def _plain_lines(text: str) -> list[dict]:
    """Non-tab text into verse lines, chords kept where the site put them."""
    lines: list[dict] = []
    for raw_line in text.split("\n"):
        line_text, chords = _scan_line(raw_line)
        line_text = line_text.rstrip()
        if not line_text.strip() and not chords:
            continue
        lines.append({"kind": "verse", "text": line_text, "chords": chords})
    return lines


def _parse_pre_text(content: str) -> list[dict]:
    """The raw chart text the ``T`` row carries.

    Tabs are marked up as ``#t1# ... #/t1#`` with their tablature in a
    ``#t2# ... #/t2#`` span; each becomes one tab line. Everything else is
    verse lines. The chart is rendered monospace, so the text keeps the
    padding the site put in.
    """
    lines: list[dict] = []
    tab_pattern = re.compile(r"#t1#(.*?)#/t1#", re.S)
    cursor = 0
    for match in tab_pattern.finditer(content):
        lines.extend(_plain_lines(content[cursor : match.start()]))
        block = match.group(1).replace("#t2#", "").replace("#/t2#", "")
        tab_text, tab_chords = _scan_line(block)
        lines.append({"kind": "tab", "text": tab_text.rstrip(), "chords": tab_chords})
        cursor = match.end()
    lines.extend(_plain_lines(content[cursor:]))
    return lines


def parse_chart(page: str) -> dict:
    """The song chart out of a fetched chart page.

    Returns the source metadata and the structured chart: ``lines`` for
    rendering, and ``chords`` — the flat, in-order chord labels of the verse
    lines only, which is the sequence the audio analysis is compared against.
    """
    flight = _decode_flight(page)
    if not flight:
        raise CifraclubError("the chart data could not be read from the page")

    song_data, rows = _song_data(flight)
    content_ref = str(song_data.get("content", ""))
    row = rows.get(content_ref[1:])
    if not row:
        raise CifraclubError("the chart data could not be read from the page")
    content = _content_of(row)

    if isinstance(content, str):
        lines = _parse_pre_text(content)
    else:
        lines = _build_lines(content)
    if not lines:
        raise CifraclubError("the page did not contain a chart")

    chords = [
        chord["name"]
        for line in lines
        if line["kind"] == "verse"
        for chord in line["chords"]
    ]

    artist = song_data.get("artist") or {}
    title = song_data.get("title") or ""
    if not title:
        match = _OG_TITLE_PATTERN.search(page)
        if match:
            parts = [p.strip() for p in match.group(1).split(" - ")]
            title = parts[0]
            if not artist.get("name") and len(parts) > 1:
                artist = dict(artist)
                artist["name"] = " - ".join(parts[1:])

    key_match = _TOM_KEY_PATTERN.search(page)
    image_match = _OG_IMAGE_PATTERN.search(page)

    return {
        "source": {
            "id": song_data.get("id"),
            "title": title,
            "artist": artist.get("name") or "",
            "album": artist.get("album") or "",
            "image": image_match.group(1) if image_match else artist.get("image") or "",
            "key": key_match.group(1) if key_match else "",
            "composers": song_data.get("composers") or [],
        },
        "lines": lines,
        "chords": chords,
    }


def fetch_chart(dns: str, url: str) -> dict:
    """Fetch and parse the chart at ``/dns/url/``."""
    page_url = PAGE_URL.format(dns=dns, url=url)
    page = _fetch(page_url)
    return parse_chart(page)


# Verdict names for one comparison between the web chart and the detected
# analysis.
VERDICT_MATCH = "match"
VERDICT_PARTIAL = "partial"
VERDICT_DIFF = "diff"
VERDICT_MISSING = "missing"
VERDICT_UNKNOWN = "unknown"
VERDICT_NO_CHORD = "noChord"

_VERDICTS = (VERDICT_MATCH, VERDICT_PARTIAL, VERDICT_DIFF, VERDICT_MISSING, VERDICT_UNKNOWN)


def _detected_spans(analysis: dict) -> list[dict]:
    """The detected chord spans as a comparable list, keeping their origin.

    Only spans with a readable root take part in the alignment; the no-chord
    spans are transparent to it. ``originalIndex`` keeps the tie back to the
    analysis they came from, so a corrected analysis can be rebuilt in place.
    """
    from .analysis import cifra, theory

    spans: list[dict] = []
    for index, span in enumerate(analysis.get("chords", [])):
        chord = theory.parse_label(str(span.get("label", "")))
        if chord is None or chord.root is None:
            continue
        spans.append(
            {
                "originalIndex": index,
                "start": float(span.get("start", 0.0)),
                "end": float(span.get("end", 0.0)),
                "startBeat": span.get("startBeat"),
                "endBeat": span.get("endBeat"),
                "label": span.get("label", ""),
                "root": chord.root,
                "quality": chord.quality,
                "reduced": theory.Chord(chord.root, cifra.simplify_quality(chord.quality)),
            }
        )
    return spans


def _align_web(spans: list[dict], web: list[dict | None]) -> dict[int, int]:
    """Which web chord each detected span lines up with.

    A global sequence alignment (Needleman-Wunsch) over the reduced roots and
    qualities, so an extra chord or a dropped one shifts the neighbours instead
    of mispairing everything after it. Returns ``{span index: web index}``,
    with only the web chords that could be read taking part.
    """
    from .analysis import cifra, theory

    det = [span["reduced"] for span in spans]
    valid = [
        (index, theory.Chord(norm["root"], cifra.simplify_quality(norm["quality"])))
        for index, norm in enumerate(web)
        if norm is not None
    ]

    aligned: dict[int, int] = {}
    if not det or not valid:
        return aligned
    rows, cols = len(det), len(valid)
    dp = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(1, rows + 1):
        dp[i][0] = -i
    for j in range(1, cols + 1):
        dp[0][j] = -j
    for i in range(1, rows + 1):
        di = det[i - 1]
        for j in range(1, cols + 1):
            wj = valid[j - 1][1]
            if di.root == wj.root:
                diagonal = 2 if di.quality == wj.quality else 0
            else:
                diagonal = -2
            dp[i][j] = max(dp[i - 1][j - 1] + diagonal, dp[i - 1][j] - 1, dp[i][j - 1] - 1)
    i, j = rows, cols
    while i > 0 and j > 0:
        di = det[i - 1]
        wj = valid[j - 1][1]
        if di.root == wj.root:
            diagonal = 2 if di.quality == wj.quality else 0
        else:
            diagonal = -2
        if dp[i][j] == dp[i - 1][j - 1] + diagonal:
            aligned[i - 1] = valid[j - 1][0]
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j] - 1:
            i -= 1
        else:
            j -= 1
    return aligned


def _parse_key(label: str | None) -> tuple[int, str] | None:
    """The chart's ``tom`` (``"G"``, ``"Em"``, ``"Bbm"``...) as ``(tonic, mode)``."""
    from .analysis import theory

    label = (label or "").strip()
    if not label:
        return None
    match = _ROOT_PATTERN.match(label)
    if not match:
        return None
    tonic = theory.NAME_TO_PC.get(match.group(1).lower())
    if tonic is None:
        return None
    mode = "minor" if match.group(2).strip().lower().startswith("m") else "major"
    return tonic, mode


def compare(analysis: dict, web_chords: list[str]) -> dict:
    """Judge the web chart against the detected audio analysis.

    Both sides speak the same harmonic language but not the same vocabulary or
    the same length: the chart is what the site's editor wrote, the detection
    is what the decoder heard, and the two disagree on which chords happen,
    how many times, and with what voicing. So the detected chord spans are
    aligned to the web chord sequence with a global sequence alignment — the
    same decision procedure as comparing two spellings of a word — and every
    span gets a verdict.

    A span that maps to no web chord is ``missing`` (the chart does not write
    a chord the audio plainly plays); a web chord that maps to no span is
    reported through ``stats`` and the alignment rather than as its own row.
    Root-only agreement is ``partial``: a ``C`` where the chart writes ``C7M``
    is the same harmony under a different name. A different root is ``diff``.
    A label the site's own notation defeats is ``unknown``.

    A per-bar view is derived from the last beat of each bar, so a renderer
    that draws the chart in bars can colour a cell without knowing about times.
    """
    from .analysis import cifra, theory

    use_flats = bool(analysis.get("useFlats"))

    spans = _detected_spans(analysis)
    web = [normalize_label(label) for label in web_chords]
    aligned = _align_web(spans, web)

    verdicts: list[dict] = []
    for index, span in enumerate(spans):
        web_index = aligned.get(index)
        web_norm = web[web_index] if web_index is not None else None
        if web_norm is None:
            verdict = VERDICT_MISSING
        else:
            # Compare the written letters, not the reduced chords: a G where
            # the chart writes G7M shares the root but not the letter, so it
            # is "próximo" rather than "casa".
            if web_norm["root"] == span["root"] and web_norm["quality"] == span["quality"]:
                verdict = VERDICT_MATCH
            elif web_norm["root"] == span["root"]:
                verdict = VERDICT_PARTIAL
            else:
                verdict = VERDICT_DIFF
        verdicts.append(
            {
                "start": span["start"],
                "end": span["end"],
                "startBeat": span["startBeat"],
                "endBeat": span["endBeat"],
                "detected": cifra.br_label(span["label"], use_flats),
                "web": web_chords[web_index] if web_index is not None else None,
                "verdict": verdict,
            }
        )

    per_bar: list[dict] = []
    last_by_bar: dict[int, dict] = {}
    for beat in analysis.get("beats", []):
        last_by_bar[int(beat.get("bar", 1))] = beat
    for bar in sorted(last_by_bar):
        beat = last_by_bar[bar]
        beat_chord = theory.parse_label(str(beat.get("label", "")))
        if beat_chord is None or beat_chord.root is None:
            per_bar.append({"bar": bar, "detected": None, "web": None, "verdict": VERDICT_NO_CHORD})
            continue
        time = float(beat.get("time", 0.0))
        verdict = VERDICT_MISSING
        web_label: str | None = None
        for span in verdicts:
            if span["start"] <= time < span["end"]:
                verdict = span["verdict"]
                web_label = span["web"]
                break
        per_bar.append(
            {
                "bar": bar,
                "detected": cifra.br_label(beat.get("label", ""), use_flats),
                "web": web_label,
                "verdict": verdict,
            }
        )

    stats: dict[str, int] = {name: 0 for name in _VERDICTS}
    for span in verdicts:
        stats[span["verdict"]] += 1
    stats[VERDICT_UNKNOWN] = sum(1 for norm in web if norm is None)
    stats["total"] = len(web_chords)
    stats["detected"] = len(spans)

    return {"verdicts": verdicts, "perBar": per_bar, "stats": stats}


def correct(analysis: dict, web_chords: list[str], web_key: str = "") -> dict:
    """Rewrite the detected analysis with the chart as the authority.

    The detected chord letters become the chart's: every span the alignment
    ties to a written chord takes that chord's root and quality, and the tom
    becomes the chart's key. Everything that describes *when* — beats, bars,
    timing and confidence — comes from the audio and is kept. Returns a new
    analysis dict; the caller persists it.
    """
    from .analysis import theory

    web = [normalize_label(label) for label in web_chords]
    spans = _detected_spans(analysis)
    aligned = _align_web(spans, web)

    by_original: dict[int, theory.Chord] = {}
    for span_index, web_index in aligned.items():
        norm = web[web_index]
        if norm is None:
            continue
        by_original[spans[span_index]["originalIndex"]] = theory.Chord(norm["root"], norm["quality"])

    parsed_key = _parse_key(web_key)
    if parsed_key is not None:
        key_tonic, key_mode = parsed_key
        key_confidence = 1.0
    else:
        existing = analysis.get("key") or {}
        key_tonic = int(existing.get("tonic", 0))
        key_mode = existing.get("mode", "major")
        key_confidence = float(existing.get("confidence", 0.0))

    corrected = copy.deepcopy(analysis)
    use_flats = theory.key_uses_flats(key_tonic, key_mode)
    corrected["useFlats"] = use_flats
    corrected["key"] = {
        "tonic": key_tonic,
        "mode": key_mode,
        "name": theory.key_name(key_tonic, key_mode),
        "confidence": round(key_confidence, 3),
    }

    spans_out: list[dict] = []
    for index, span in enumerate(corrected["chords"]):
        chord = by_original.get(index)
        if chord is None:
            parsed = theory.parse_label(str(span.get("label", "")))
            chord = parsed if parsed is not None else theory.NO_CHORD
        span = dict(span)
        span["root"] = chord.root
        span["quality"] = chord.quality
        span["label"] = chord.label(use_flats)
        span["notes"] = list(chord.pitch_classes())
        spans_out.append(span)
    corrected["chords"] = spans_out

    beats_out: list[dict] = []
    for beat in corrected["beats"]:
        rewritten = dict(beat)
        for span in spans_out:
            start, end = span.get("startBeat"), span.get("endBeat")
            if start is None or end is None:
                continue
            if int(start) <= int(rewritten["index"]) <= int(end):
                rewritten["root"] = span["root"]
                rewritten["quality"] = span["quality"]
                rewritten["label"] = span["label"]
                rewritten["notes"] = span["notes"]
                break
        beats_out.append(rewritten)
    corrected["beats"] = beats_out

    corrected["uniqueChords"] = sorted(
        {span["label"] for span in corrected["chords"] if span.get("root") is not None}
    )
    return corrected


def chart_lyric_lines(chart: dict) -> list[str]:
    """The sung words of a web chart, chords and section tags stripped.

    The chart keeps the chord names inline at the columns the site spaced them
    into, so each chord is removed exactly where ``col`` says it sits; section
    markers like ``[Intro]`` are dropped and the leftover whitespace collapses.
    The result is what a person would actually sing.
    """
    lines: list[str] = []
    for line in chart.get("lines", []):
        if line.get("kind") != "verse":
            continue
        text = line.get("text", "")
        for chord in line.get("chords", []):
            col = chord.get("col")
            name = chord.get("name", "")
            if isinstance(col, int) and name:
                text = text[:col] + " " * len(name) + text[col + len(name) :]
        text = re.sub(r"\[[^\]]*\]", " ", text)
        text = " ".join(text.split())
        if text:
            lines.append(text)
    return lines


def correct_lyrics(chart: dict, previous: dict | None) -> dict | None:
    """The chart's sung words rebuilt over the transcription's timing.

    Returns ``None`` when the chart carries no lyric text, or when there is no
    transcription to give the correction a timing skeleton. When the
    transcription has exactly one segment per chart line, each line keeps the
    segment's own start and end — phrase timing survives the swap word for
    word. When the counts disagree, the lines are laid across the sung span in
    proportion to how long each one reads, because that is the next-best guess
    for where a line of a given length starts singing.
    """
    from .analysis import lyrics as lyrics_module

    chart_lines = chart_lyric_lines(chart)
    if not chart_lines:
        return None
    previous = dict(previous or {})
    segments = previous.get("segments") or []
    if not segments:
        return None

    if len(segments) == len(chart_lines):
        rebuilt_segments = [
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": text,
            }
            for segment, text in zip(segments, chart_lines)
        ]
    else:
        begin = min(float(segment.get("start", 0.0)) for segment in segments)
        finish = max(float(segment.get("end", 0.0)) for segment in segments)
        if finish <= begin:
            finish = begin + 1.0
        span = finish - begin
        # A line's words take roughly as long as they are long, so weight by
        # character count with a floor that gives short lines a beat of their
        # own.
        weights = [len("".join(line.split())) + 1 for line in chart_lines]
        total = sum(weights) or 1
        cursor = begin
        rebuilt_segments = []
        for line, weight in zip(chart_lines, weights):
            end = cursor + span * (weight / total)
            rebuilt_segments.append(
                {"start": round(cursor, 3), "end": round(end, 3), "text": line}
            )
            cursor = end

    corrected = lyrics_module.rebuild_from_segments(rebuilt_segments, previous)
    corrected["correctedByChart"] = True
    return corrected
