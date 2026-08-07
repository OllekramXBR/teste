"""Search and download tracks from mp3.pm.

mp3.pm is a search engine over public MP3 files. A query becomes a subdomain of
the site — "legiao urbana" is s-legiao-urbana.mp3.pm — and the page it serves
is plain HTML: one ``<li class="cplayer-sound-item">`` per result, each
carrying the direct MP3 address in a ``data-download-url`` attribute. The whole
protocol is to fetch that page, pull the results out, and download the chosen
one.

The module only ever talks to mp3.pm, with URLs it built itself. A client can
name a song but never a destination, which is what keeps a "download this for
me" endpoint from becoming a way to make the server fetch an arbitrary URL.
"""

from __future__ import annotations

import html
import logging
import re
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import MUSIC_DIR

logger = logging.getLogger(__name__)

SEARCH_HOST = "mp3.pm"
# The site answers a plain curl without one, but serving a browser-ish header
# keeps its edge servers from treating the download as a bot and refusing it.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
# A four-minute track at 320kbps is roughly 60 MB. Generous enough for a long
# mix or an inflated stream, small enough that a wedged download cannot fill
# the data volume.
MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024
# mp3.pm serves fifty results a page; a second page nearly always closes the
# gaps a query leaves behind (a misspelling, an artist that ships two masters).
# Three is the polite ceiling — we are a guest, and each page is another fetch.
SEARCH_PAGES = 2
# A small pause between page fetches, so a search does not hammer the site the
# way a loop over its own subdomains would.
PAGE_DELAY_SECONDS = 0.4

# Each result block begins with the <li> and carries its own attributes, so the
# page is split on the opening tag and every chunk parsed on its own.
_ITEM_OPEN = '<li class="cplayer-sound-item"'
_ID_PATTERN = re.compile(r'data-sound-id="(\d+)"')
_DOWNLOAD_URL_PATTERN = re.compile(r'data-download-url="([^"]+)"')
# The listen URL is the same file served as a stream, which is what the search
# preview plays in the browser before anything is downloaded.
_LISTEN_URL_PATTERN = re.compile(r'data-sound-url="([^"]+)"')
_AUTHOR_PATTERN = re.compile(r'cplayer-data-sound-author">([^<]*)</i>', re.IGNORECASE)
_TITLE_PATTERN = re.compile(r'cplayer-data-sound-title">([^<]*)</b>', re.IGNORECASE)
_TIME_PATTERN = re.compile(r'cplayer-data-sound-time">([^<]*)</em>', re.IGNORECASE)

CHUNK_SIZE = 256 * 1024


class Mp3pmError(RuntimeError):
    """The site was unreachable, or returned something unreadable."""


@dataclass
class Track:
    """One search result, with everything needed to preview or download it."""

    sound_id: str
    title: str
    artist: str
    duration: int  # seconds
    download_url: str
    listen_url: str = ""

    def to_dict(self) -> dict:
        return {
            "soundId": self.sound_id,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "downloadUrl": self.download_url,
            "listenUrl": self.listen_url,
        }


def _slug(query: str) -> str:
    """The subdomain form of a query: accents dropped, words joined by dashes."""
    decomposed = unicodedata.normalize("NFKD", query.lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "-".join(word for word in re.split(r"[^a-z0-9]+", ascii_text) if word)


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError:
        # Not wrapped: 404 means "nothing matched" and the caller decides what
        # that means, while every other status is an error it re-raises.
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise Mp3pmError(f"mp3.pm is unreachable: {error}") from error


def _parse_duration(text: str) -> int:
    """'06:47' or '1:02:03' into seconds."""
    seconds = 0
    for part in text.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def _parse_page(page: str) -> list[Track]:
    """Turn the result list HTML into ``Track`` objects."""
    tracks: list[Track] = []
    for chunk in page.split(_ITEM_OPEN)[1:]:
        id_match = _ID_PATTERN.search(chunk)
        url_match = _DOWNLOAD_URL_PATTERN.search(chunk)
        if not id_match or not url_match:
            continue

        listen_match = _LISTEN_URL_PATTERN.search(chunk)
        title_match = _TITLE_PATTERN.search(chunk)
        author_match = _AUTHOR_PATTERN.search(chunk)
        time_match = _TIME_PATTERN.search(chunk)

        title = html.unescape(title_match.group(1).strip()) if title_match else ""
        artist = html.unescape(author_match.group(1).strip()) if author_match else ""
        duration = _parse_duration(time_match.group(1)) if time_match else 0

        tracks.append(
            Track(
                sound_id=id_match.group(1),
                title=title or "Sem título",
                artist=artist,
                duration=duration,
                download_url=url_match.group(1),
                listen_url=listen_match.group(1) if listen_match else "",
            )
        )
    return tracks


def _dedupe(tracks: list[Track]) -> list[Track]:
    """Drop repeats of the same recording across pages.

    The id is what mp3.pm itself uses to tell recordings apart, so it is the
    dedupe key: a page boundary must not show the same track twice, while two
    genuinely different masters of the same song (a live take and the studio
    one, say) keep their separate rows.
    """
    seen: set[str] = set()
    unique: list[Track] = []
    for track in tracks:
        if track.sound_id in seen:
            continue
        seen.add(track.sound_id)
        unique.append(track)
    return unique


def search(query: str, limit: int = 20, pages: int = SEARCH_PAGES) -> list[Track]:
    """The top results for a query, as served by mp3.pm.

    An empty query or one that normalises to nothing returns no results. mp3.pm
    answers 404 when nothing matches, which is a valid outcome rather than an
    error, so that alone yields an empty list. Each page is fetched separately
    with a pause between them, and results are deduplicated before being cut to
    the limit.
    """
    slug = _slug(query)
    if not slug:
        return []

    page_count = min(max(pages, 1), 5)
    raw: list[Track] = []
    for number in range(1, page_count + 1):
        path = f"/page/{number}/" if number > 1 else "/"
        url = f"https://s-{slug}.{SEARCH_HOST}{path}"
        try:
            page = _fetch(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                if number > 1:
                    # A query can match page one and run out after it.
                    break
                logger.info("mp3.pm has nothing for %r", query)
                return []
            raise Mp3pmError(f"mp3.pm answered HTTP {error.code}") from error
        raw.extend(_parse_page(page))
        if number < page_count:
            time.sleep(PAGE_DELAY_SECONDS)

    return _dedupe(raw)[:limit]


def find(query: str, sound_id: str) -> Track | None:
    """Re-locate a result by its id on a fresh search.

    The id is the only thing a client sends back. The download URL is fetched
    again here rather than accepted from the client, so a result the server
    itself never served cannot be used to point the download anywhere.
    """
    for track in search(query):
        if track.sound_id == sound_id:
            return track
    return None


def _safe_filename(track: Track) -> str:
    """A filename a share can hold: artist - title, ASCII, no separators."""
    name = " - ".join(part for part in (track.artist, track.title) if part) or "track"
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[\\/:*?"<>|]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "track"


def _is_mp3_header(chunk: bytes) -> bool:
    """Whether the start of a stream is a real MPEG audio file.

    An ID3 tag announces most files outright; the rest start with the frame
    sync that begins every MPEG audio frame. Anything else — an HTML error
    page, a CAPTCHA, a plain-text redirect — is refused rather than saved, so a
    wedged upstream cannot drop junk into a library that expects audio.
    """
    if chunk[:3] == b"ID3":
        return True
    if len(chunk) < 2:
        return False
    # 11 bits of sync: 0xFF in the first byte, then 111xxxxx. The version and
    # layer nibbles each have a reserved value (version 01, layer 00) that a
    # real frame never carries.
    return (
        chunk[0] == 0xFF
        and (chunk[1] & 0xE0) == 0xE0
        and (chunk[1] & 0x18) != 0x08
        and (chunk[1] & 0x06) != 0x00
    )


def download(track: Track, destination: Path | None = None) -> Path:
    """Stream ``track``'s MP3 into the music folder.

    Returns the path of the saved file. The name comes from the artist and the
    title, so the file already reads well in a share someone browses by hand.
    A partial, empty, or non-audio download is removed rather than left to
    confuse the library later.
    """
    folder = destination or MUSIC_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{_safe_filename(track)}.mp3"

    request = urllib.request.Request(track.download_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            with target.open("wb") as handle:
                first = response.read(CHUNK_SIZE)
                if not _is_mp3_header(first):
                    raise Mp3pmError(
                        "the download did not return an MP3 file "
                        f"(Content-Type: {response.headers.get_content_type() or 'unknown'})"
                    )
                copied = len(first)
                if copied > MAX_DOWNLOAD_BYTES:
                    raise Mp3pmError("the download exceeds the size limit")
                handle.write(first)
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > MAX_DOWNLOAD_BYTES:
                        raise Mp3pmError("the download exceeds the size limit")
                    handle.write(chunk)
    except Mp3pmError:
        target.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        target.unlink(missing_ok=True)
        raise Mp3pmError(f"download failed: {error}") from error

    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise Mp3pmError("the download produced an empty file")

    logger.info("downloaded %s from mp3.pm", target.name)
    return target
