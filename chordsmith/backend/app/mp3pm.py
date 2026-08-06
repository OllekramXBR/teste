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

# Each result block begins with the <li> and carries its own attributes, so the
# page is split on the opening tag and every chunk parsed on its own.
_ITEM_OPEN = '<li class="cplayer-sound-item"'
_ID_PATTERN = re.compile(r'data-sound-id="(\d+)"')
_DOWNLOAD_URL_PATTERN = re.compile(r'data-download-url="([^"]+)"')
_AUTHOR_PATTERN = re.compile(r'cplayer-data-sound-author">([^<]*)</i>', re.IGNORECASE)
_TITLE_PATTERN = re.compile(r'cplayer-data-sound-title">([^<]*)</b>', re.IGNORECASE)
_TIME_PATTERN = re.compile(r'cplayer-data-sound-time">([^<]*)</em>', re.IGNORECASE)

CHUNK_SIZE = 256 * 1024


class Mp3pmError(RuntimeError):
    """The site was unreachable, or returned something unreadable."""


@dataclass
class Track:
    """One search result, with everything needed to download it."""

    sound_id: str
    title: str
    artist: str
    duration: int  # seconds
    download_url: str

    def to_dict(self) -> dict:
        return {
            "soundId": self.sound_id,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration,
            "downloadUrl": self.download_url,
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
            )
        )
    return tracks


def search(query: str, limit: int = 20) -> list[Track]:
    """The top results for a query, as served by mp3.pm.

    An empty query or one that normalises to nothing returns no results. mp3.pm
    answers 404 when nothing matches, which is a valid outcome rather than an
    error, so that alone yields an empty list.
    """
    slug = _slug(query)
    if not slug:
        return []

    url = f"https://s-{slug}.{SEARCH_HOST}/"
    try:
        page = _fetch(url)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            logger.info("mp3.pm has nothing for %r", query)
            return []
        raise Mp3pmError(f"mp3.pm answered HTTP {error.code}") from error
    return _parse_page(page)[:limit]


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


def download(track: Track, destination: Path | None = None) -> Path:
    """Stream ``track``'s MP3 into the music folder.

    Returns the path of the saved file. The name comes from the artist and the
    title, so the file already reads well in a share someone browses by hand.
    A partial or empty download is removed rather than left to confuse the
    library later.
    """
    folder = destination or MUSIC_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{_safe_filename(track)}.mp3"

    request = urllib.request.Request(track.download_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            with target.open("wb") as handle:
                copied = 0
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
