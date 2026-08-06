"""Render an analysis as a *cifra* in the Brazilian convention.

Two things separate a cifra from the chord grid the app already draws, and
neither is decoration.

**Notation.** A Brazilian chart writes ``G7M`` where an English one writes
``Gmaj7``, ``B°`` for a diminished chord and ``C+`` for an augmented one. The
note letters are the same — a cifra uses C D E F G A B, not dó ré mi — so only
the quality suffix has to be translated. The mapping is in :data:`BR_QUALITY`.

**Layout.** The chord label sits on its own line, directly above the syllable
where the change lands. That vertical alignment is the whole point of the
format: the player reads down, not across. It only works in a monospaced font,
so everything here counts characters rather than pixels, and the renderer never
lets two labels touch — a chord pushed right by its neighbour is still readable,
a chord overlapping one is not.

The lyric side is optional. Without a transcription this falls back to a
bar-per-cell grid, which is what a cifra looks like for an instrumental anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import theory

# Quality suffix as written in Brazil, keyed by the internal name.
#
# Two of these are judgement calls worth naming. Brazilian charts overwhelmingly
# write "°" for the diminished *seventh*, and the diminished triad is rare
# enough that most charts never distinguish them; "°7" is written out here so a
# reader can tell which one the decoder actually chose. And "sus4"/"sus2" are
# kept spelled out rather than the terser "4"/"2" also seen in Brazil, because
# "C4" reads as a chord degree to about half of players.
BR_QUALITY: dict[str, str] = {
    "": "",
    "m": "m",
    "7": "7",
    "m7": "m7",
    "maj7": "7M",
    "sus4": "sus4",
    "sus2": "sus2",
    "6": "6",
    "m6": "m6",
    "dim": "°",
    "aug": "+",
    "m7b5": "m7(b5)",
    "dim7": "°7",
}

# What each quality becomes when the chart is simplified. Diminished and
# augmented stay: they are rare enough that the decoder emitting one is usually
# meaningful, and a player fingers them differently from any triad.
SIMPLE_QUALITY: dict[str, str] = {
    "": "",
    "m": "m",
    "7": "",
    "m7": "m",
    "maj7": "",
    "sus4": "",
    "sus2": "",
    "6": "",
    "m6": "m",
    "dim": "dim",
    "aug": "aug",
    "m7b5": "m",
    "dim7": "dim",
}

# How wide a lyric line may get before it is broken. Chosen so a line plus its
# chord row still fits an A4 page and a phone screen in portrait.
LINE_WIDTH = 52

# A silence longer than this between two sung words ends the line, whatever its
# width. Roughly a bar at a slow tempo: shorter than this and the singer is
# still inside the phrase.
PHRASE_GAP = 1.1

# An instrumental stretch shorter than this is not worth its own block; the
# chords in it are attached to the line that follows.
INSTRUMENTAL_GAP = 3.0

MODE_PT = {"major": "maior", "minor": "menor"}


def br_quality(quality: str) -> str:
    """Brazilian suffix for an internal quality name."""
    return BR_QUALITY.get(quality, quality)


def br_label(label: str, use_flats: bool = False) -> str:
    """Rewrite one chord label in Brazilian notation.

    Unparseable labels are returned untouched — better a chart with one odd
    symbol than a crash, and "N" (no chord) is meant to survive as-is so the
    caller can filter it.
    """
    chord = theory.parse_label(label)
    if chord is None or chord.root is None:
        return label
    names = theory.FLAT_NAMES if use_flats else theory.SHARP_NAMES
    return f"{names[chord.root]}{br_quality(chord.quality)}"


@dataclass
class Word:
    text: str
    start: float
    end: float
    # Index of the transcribed phrase this word came from; -1 when unknown.
    phrase: int = -1


@dataclass
class ChordHit:
    """A chord change at a point in time, already labelled for printing."""

    label: str
    start: float


@dataclass
class Line:
    """One lyric line and the chords that land over it."""

    words: list[Word] = field(default_factory=list)
    chords: list[ChordHit] = field(default_factory=list)
    tag: str = ""

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0


def simplify_quality(quality: str) -> str:
    """Reduce a quality to the triad a player would actually strum.

    A chroma decoder reads a passing note in the melody as an added sixth, a
    suspended fourth, a major seventh — and each of those is defensible frame by
    frame while being wrong about the song. Printing them turns a three-chord
    verse into a chart with a dozen symbols, which is worse than useless: the
    reader stops trusting it.

    So this keeps only what changes the shape of the hand. Major and minor
    survive; diminished and augmented survive because a player really does
    finger those differently; everything else collapses to its triad.
    """
    return SIMPLE_QUALITY.get(quality, quality)


def _simplified_spans(spans: list[dict], min_seconds: float) -> list[dict]:
    """Collapse extensions, drop flickers, then merge what became identical.

    The three steps are in that order for a reason. Simplifying first is what
    makes a C6 followed by a C mergeable at all; merging before dropping would
    leave a one-beat D# sitting between two G's as its own span; and dropping
    before merging means the neighbours close the hole themselves.
    """
    simplified: list[dict] = []
    for span in spans:
        chord = theory.parse_label(span.get("label", ""))
        if chord is None or chord.root is None:
            continue
        quality = simplify_quality(chord.quality)
        simplified.append(
            {
                **span,
                "label": theory.Chord(chord.root, quality).label(),
                "start": float(span.get("start", 0.0)),
                "end": float(span.get("end", 0.0)),
            }
        )

    kept = [
        span for span in simplified if span["end"] - span["start"] >= min_seconds
    ] or simplified

    merged: list[dict] = []
    for span in kept:
        if merged and merged[-1]["label"] == span["label"]:
            merged[-1]["end"] = span["end"]
        else:
            merged.append(dict(span))
    return merged


def _chord_hits(
    analysis: dict, transpose: int, capo: int, simplify: bool = True
) -> list[ChordHit]:
    """Chord changes from the analysis, transposed, capoed and translated.

    Order matters: transposition changes the key the song is *heard* in, the
    capo only changes the shape the hand makes. So the capo is applied last, to
    labels that already carry the transposition.
    """
    use_flats = bool(analysis.get("useFlats"))
    spans = [
        span
        for span in analysis.get("chords", [])
        if span.get("label") and span.get("label") != theory.NO_CHORD_LABEL
    ]

    if simplify:
        # One beat. A chord that does not last a single beat is, in this
        # decoder's output, almost always a frame or two of a passing tone
        # rather than a change the player is meant to make.
        bpm = float(analysis.get("bpm") or 0) or 120.0
        spans = _simplified_spans(spans, min_seconds=60.0 / bpm)

    hits: list[ChordHit] = []
    for span in spans:
        label = span["label"]
        if transpose:
            label = theory.transpose_label(label, transpose, use_flats)
        if capo:
            label = theory.capo_shift([label], capo, use_flats)[0]
        hits.append(ChordHit(label=br_label(label, use_flats), start=float(span["start"])))
    return hits


def _words(lyrics: dict | None) -> list[Word]:
    if not lyrics:
        return []
    segments = [
        (float(segment.get("start", 0.0)), float(segment.get("end", 0.0)))
        for segment in (lyrics.get("segments") or [])
    ]
    words: list[Word] = []
    for entry in lyrics.get("words", []):
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        start = float(entry.get("start", 0.0))
        words.append(
            Word(
                text=text,
                start=start,
                end=float(entry.get("end", 0.0)),
                phrase=_phrase_of(start, segments),
            )
        )
    return words


def _phrase_of(start: float, segments: list[tuple[float, float]]) -> int:
    """Index of the transcribed segment a word belongs to.

    The recogniser already decided where one sung phrase ends and the next
    begins; that judgement is better than any silence threshold measured after
    the fact, because it accounts for a singer who runs two lines together.
    ``-1`` means no segment covers this word, which puts it with its neighbours.
    """
    for index, (begin, finish) in enumerate(segments):
        if begin - 0.05 <= start <= finish + 0.05:
            return index
    return -1


def _break_into_lines(words: list[Word]) -> list[Line]:
    """Group words into printable lines.

    A new transcribed phrase always starts a new line. Inside a phrase the line
    is broken on a long silence, and failing that on width — a line broken
    mid-phrase reads worse than a short one, but an over-long line does not fit
    the page at all.
    """
    lines: list[Line] = []
    current = Line()
    width = 0
    for word in words:
        previous = current.words[-1] if current.words else None
        gap = word.start - previous.end if previous else 0.0
        new_phrase = previous is not None and word.phrase != previous.phrase and word.phrase >= 0
        too_wide = width + len(word.text) + 1 > LINE_WIDTH
        if current.words and (new_phrase or gap > PHRASE_GAP or too_wide):
            lines.append(current)
            current, width = Line(), 0
        current.words.append(word)
        width += len(word.text) + (1 if width else 0)
    if current.words:
        lines.append(current)
    return lines


def _assign_chords(lines: list[Line], hits: list[ChordHit], lead_in: float) -> list[Line]:
    """Attach every chord change to a line, inventing chord-only lines as needed.

    A chord belongs to the line whose sung words it sits under. Chords that fall
    in a long silence — an intro, a solo, the space between verses — belong to no
    line, so they get one of their own rather than being crammed onto whichever
    lyric happens to be adjacent.
    """
    if not lines:
        return [Line(chords=hits, tag="Instrumental")] if hits else []

    result: list[Line] = []
    index = 0
    previous_end = 0.0

    for position, line in enumerate(lines):
        # The chords for this line start at the previous line's last word, so a
        # change made while the singer breathes still prints above the line it
        # prepares — that is where a player expects to read it.
        window_start = previous_end if position else -1.0
        pending: list[ChordHit] = []
        while index < len(hits) and hits[index].start < line.end:
            if hits[index].start >= window_start:
                pending.append(hits[index])
            index += 1

        gap = line.start - previous_end if position else line.start - lead_in
        if pending and gap > INSTRUMENTAL_GAP:
            # Long silence before this line: the chords played during it are an
            # intro or a break, not an accompaniment to the words.
            during_gap = [hit for hit in pending if hit.start < line.start - PHRASE_GAP]
            if during_gap:
                tag = "Intro" if position == 0 else "Instrumental"
                result.append(Line(chords=during_gap, tag=tag))
                pending = [hit for hit in pending if hit not in during_gap]

        line.chords = pending
        result.append(line)
        previous_end = line.end

    if index < len(hits):
        result.append(Line(chords=hits[index:], tag="Final"))
    return result


def _tag_solos(lines: list[Line], analysis: dict) -> None:
    """Mark chord-only blocks that overlap a detected solo section."""
    solos = [
        (float(section.get("start", 0.0)), float(section.get("end", 0.0)))
        for section in (analysis.get("lead") or {}).get("sections", [])
        if section.get("isSolo")
    ]
    if not solos:
        return
    for line in lines:
        # "Intro" is left alone on purpose: an intro is very often a lead line,
        # so the solo detector fires on it, and relabelling the opening of the
        # song as a solo tells the player something false about the form.
        if line.words or not line.chords or line.tag not in ("Instrumental", "Final"):
            continue
        start = line.chords[0].start
        end = line.chords[-1].start
        if any(solo_start <= end and start <= solo_end for solo_start, solo_end in solos):
            line.tag = "Solo"


def _render_line(line: Line) -> list[str]:
    """Two strings — the chord row and the lyric row — or one for a chord-only line."""
    text = ""
    columns: list[tuple[Word, int]] = []
    for word in line.words:
        if text:
            text += " "
        columns.append((word, len(text)))
        text += word.text

    chord_row = ""
    for hit in line.chords:
        column = len(chord_row) + 1 if chord_row else 0
        if columns:
            # The chord goes over the word that is sounding when it changes, or
            # over the next one if it changes in the space before that word.
            target = next(
                (col for word, col in columns if word.end > hit.start),
                columns[-1][1] + len(columns[-1][0].text) + 1,
            )
            column = max(column, target)
        chord_row += " " * (column - len(chord_row)) + hit.label

    rows = []
    if chord_row:
        rows.append(chord_row)
    if text:
        rows.append(text)
    return rows


def _grid(analysis: dict, hits: list[ChordHit], bars_per_line: int = 4) -> list[str]:
    """Fallback chart with no lyrics: chords laid out in bars, four to a line."""
    beats = analysis.get("beats", [])
    if not beats or not hits:
        return [" ".join(hit.label for hit in hits)] if hits else []

    bar_starts: dict[int, float] = {}
    for beat in beats:
        bar = int(beat.get("bar", 1))
        bar_starts.setdefault(bar, float(beat.get("time", 0.0)))

    cells: list[str] = []
    for bar in sorted(bar_starts):
        start = bar_starts[bar]
        end = bar_starts.get(bar + 1, float("inf"))
        in_bar = [hit.label for hit in hits if start <= hit.start < end]
        cells.append(" ".join(in_bar) if in_bar else "%")

    # Collapse repeats of a whole line, which is what a real chart does instead
    # of printing the same four bars eight times.
    lines: list[str] = []
    for index in range(0, len(cells), bars_per_line):
        row = cells[index : index + bars_per_line]
        width = max((len(cell) for cell in row), default=1)
        lines.append("| " + " | ".join(cell.ljust(width) for cell in row) + " |")
    return lines


def render_chordpro(
    analysis: dict,
    lyrics: dict | None = None,
    *,
    title: str = "",
    artist: str = "",
    transpose: int = 0,
    capo: int = 0,
    simplify: bool = True,
) -> str:
    """The same chart in ChordPro, with the chord inline before the syllable.

    Worth carrying alongside the columnar form for one reason: it does not
    depend on a monospaced font, or on any font at all. A cifra whose chords sit
    on their own line is only correct while the character widths hold; paste it
    into a message, a document or a phone with a different font and the chords
    drift off the words they belong to. ChordPro survives all of that, and every
    other chord application reads it.
    """
    use_flats = bool(analysis.get("useFlats"))
    key = analysis.get("key") or {}
    tonic = key.get("tonic")

    out: list[str] = []
    if title:
        out.append(f"{{title: {title}}}")
    if artist:
        out.append(f"{{artist: {artist}}}")
    if tonic is not None:
        sounding = theory.note_name(int(tonic) + transpose, use_flats)
        out.append(f"{{key: {sounding}}}")
    if capo:
        out.append(f"{{capo: {capo}}}")
    out.append("")

    hits = _chord_hits(analysis, transpose, capo, simplify=simplify)
    words = _words(lyrics)

    if not words:
        out.append("{comment: Instrumental}")
        out.extend(_grid(analysis, hits))
        return "\n".join(out).rstrip() + "\n"

    lines = _assign_chords(_break_into_lines(words), hits, lead_in=0.0)
    _tag_solos(lines, analysis)

    for line in lines:
        if line.tag:
            out.append("")
            out.append(f"{{comment: {line.tag}}}")
        if not line.words:
            out.append(" ".join(f"[{hit.label}]" for hit in line.chords))
            continue

        pieces: list[str] = []
        for index, word in enumerate(line.words):
            for hit in line.chords:
                target = next(
                    (position for position, item in enumerate(line.words) if item.end > hit.start),
                    len(line.words) - 1,
                )
                if target == index:
                    pieces.append(f"[{hit.label}]")
            pieces.append(word.text + " ")
        out.append("".join(pieces).rstrip())

    return "\n".join(out).rstrip() + "\n"


def render(
    analysis: dict,
    lyrics: dict | None = None,
    *,
    title: str = "",
    artist: str = "",
    transpose: int = 0,
    capo: int = 0,
    simplify: bool = True,
) -> str:
    """Build the full cifra as plain text.

    ``simplify`` is on by default because an unsimplified cifra of a real
    recording is not a usable chart — see :func:`simplify_quality`. Turn it off
    to read exactly what the decoder produced.
    """
    use_flats = bool(analysis.get("useFlats"))
    key = analysis.get("key") or {}
    tonic, mode = key.get("tonic"), key.get("mode", "major")

    header: list[str] = []
    if title:
        header.append(title)
    if artist:
        header.append(artist)
    if header:
        header.append("")

    if tonic is not None:
        sounding = theory.note_name(int(tonic) + transpose, use_flats)
        played = theory.note_name(int(tonic) + transpose - capo, use_flats)
        line = f"Tom: {sounding} {MODE_PT.get(mode, mode)}"
        if transpose:
            original = theory.note_name(int(tonic), use_flats)
            line += f"  (original: {original} {MODE_PT.get(mode, mode)})"
        header.append(line)
        if capo:
            header.append(f"Capotraste na {capo}ª casa  (formas de {played})")

    hits = _chord_hits(analysis, transpose, capo, simplify=simplify)
    unique = sorted({hit.label for hit in hits})
    if unique:
        header.append("Acordes: " + "  ".join(unique))
    header.append("")

    words = _words(lyrics)
    if not words:
        body = _grid(analysis, hits)
        if body:
            body.insert(0, "[Instrumental]")
        else:
            body = ["(sem acordes detectados)"]
        return "\n".join(header + body).rstrip() + "\n"

    lines = _assign_chords(_break_into_lines(words), hits, lead_in=0.0)
    _tag_solos(lines, analysis)

    body: list[str] = []
    for line in lines:
        if line.tag:
            if body:
                body.append("")
            body.append(f"[{line.tag}]")
        rendered = _render_line(line)
        if rendered:
            body.extend(rendered)
    return "\n".join(header + body).rstrip() + "\n"
