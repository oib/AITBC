"""Input guard for untrusted media handed to FFmpeg or PyAV (CE-001, #1170).

FFmpeg picks a demuxer by sniffing *content*, not by filename, so an upload named
``clip.mp4`` can still be an HLS playlist or concat script, and a node-chosen
``input.m3u8`` is an HLS playlist outright. A playlist is not media: it is a list of
further resources, and FFmpeg opens each one with whatever protocol the URL names.
On a shop node that turned "transcode my file" into "read any file the service user
can read" (reproduced with a ``file://`` segment) and, on builds whose default
whitelist is wider than Debian's, "request any loopback URL" as well.

Two input options close that without touching legitimate uploads:

* ``-protocol_whitelist file`` -- the input is always a local spool file, so no
  nested resource may use any other protocol (no http, ftp, rtmp, tcp, udp, data, pipe,
  subfile, crypto).
* ``-format_whitelist <demuxers>`` -- only plain container and raw-stream demuxers.
  Playlist and script demuxers (hls, dash, concat, sdp, rtsp, ffmetadata) are absent,
  so a playlist is refused before it can name a nested resource.

``ffmpeg_input_guard()`` goes immediately before ``-i``. ``pyav_open_options()`` is the
same pair for ``av.open(..., options=...)``; PyAV forwards the dict to
``avformat_open_input``, where both names are ordinary format-context options.
"""

from __future__ import annotations

PROTOCOL_WHITELIST = "file"

# Demuxer names as FFmpeg reports them (`ffmpeg -demuxers`). Grouped containers such as
# "mov,mp4,m4a,3gp,3g2,mj2" match on any member, so each member is listed.
FORMAT_WHITELIST: tuple[str, ...] = (
    # containers
    "mov",
    "mp4",
    "m4a",
    "3gp",
    "3g2",
    "mj2",
    "matroska",
    "webm",
    "avi",
    "mpegts",
    "mpeg",
    "asf",
    "flv",
    "ogg",
    "wav",
    "aiff",
    # audio streams
    "mp3",
    "aac",
    "flac",
    "ac3",
    "eac3",
    "amr",
    # raw video streams
    "h264",
    "hevc",
    "mpegvideo",
    "ivf",
    # still images and animations
    "image2",
    "png_pipe",
    "jpeg_pipe",
    "gif",
    "webp_pipe",
    "bmp_pipe",
    "tiff_pipe",
)


def format_whitelist() -> str:
    return ",".join(FORMAT_WHITELIST)


def ffmpeg_input_guard() -> list[str]:
    """Input options that belong directly before ``-i <untrusted path>``."""
    return ["-protocol_whitelist", PROTOCOL_WHITELIST, "-format_whitelist", format_whitelist()]


def pyav_open_options() -> dict[str, str]:
    """The same guard as an ``options=`` dict for ``av.open``."""
    return {"protocol_whitelist": PROTOCOL_WHITELIST, "format_whitelist": format_whitelist()}
