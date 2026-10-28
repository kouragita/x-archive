#!/usr/bin/env python3
"""x-archive: save public X posts and their media for personal archival.

Resolves a public post through X's syndication endpoint (the same one used to
render embedded posts), then downloads the highest-quality stream X stores, or
converts it to MP3.

Only public posts are reachable. Restricted, deleted or protected posts return
a tombstone and are reported as such.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; x-archive/0.1; +https://kouragita.com)"
SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result?id={id}&lang=en&token=a"


def post_id(value: str) -> str:
    m = re.search(r"(?:x|twitter)\.com/[^/\s]+/status(?:es)?/(\d{15,25})", value)
    if m:
        return m.group(1)
    if value.isdigit() and len(value) >= 15:
        return value
    raise SystemExit(f"not an X post link: {value}")


def fetch(tid: str) -> dict:
    request = urllib.request.Request(SYNDICATION.format(id=tid), headers={"user-agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"post {tid}: HTTP {error.code}")
    except urllib.error.URLError as error:
        raise SystemExit(f"post {tid}: {error.reason}")


def streams(post: dict) -> list[dict]:
    found = []
    for media in post.get("mediaDetails") or []:
        for variant in (media.get("video_info") or {}).get("variants", []):
            if variant.get("content_type") == "video/mp4" and variant.get("bitrate"):
                found.append(variant)
    return sorted(found, key=lambda v: v["bitrate"], reverse=True)


def resolution(variant: dict) -> str:
    m = re.search(r"/(\d+)x(\d+)/", variant["url"])
    return f"{m.group(2)}p" if m else "video"


def describe(post: dict, tid: str) -> None:
    user = post.get("user") or {}
    print(f"  author   @{user.get('screen_name', '?')}  ({user.get('name', '?')})")
    print(f"  posted   {post.get('created_at', '?')}")
    text = (post.get("text") or "").replace("\n", " ")
    print(f"  text     {text[:160]}")
    found = streams(post)
    print(f"  streams  {len(found)}")
    for variant in found:
        print(f"    {variant['bitrate']:>9} bps  {resolution(variant):>7}  "
              f"{variant['bitrate'] // 1000:>5} kbps")


def download(url: str, path: pathlib.Path) -> None:
    request = urllib.request.Request(url, headers={"user-agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as out:
        total = int(response.headers.get("content-length") or 0)
        done = 0
        while chunk := response.read(262_144):
            out.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total:3d}%  {done / 1_048_576:6.1f} MB", end="")
        print()


def to_mp3(video: pathlib.Path, audio: pathlib.Path) -> pathlib.Path:
    if not shutil.which("ffmpeg"):
        raise SystemExit("mp3 conversion needs ffmpeg on PATH")
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-vn", "-codec:a", "libmp3lame", "-q:a", "0", str(audio)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {result.stderr.strip()[:200]}")
    return audio


def main() -> None:
    parser = argparse.ArgumentParser(description="archive a public X post's media")
    parser.add_argument("link", help="x.com/.../status/<id> or a bare post id")
    parser.add_argument("-o", "--out", type=pathlib.Path, default=pathlib.Path("downloads"))
    parser.add_argument("--info", action="store_true", help="show the post and streams, download nothing")
    parser.add_argument("--audio", action="store_true", help="also convert the video to mp3")
    parser.add_argument("--keep-video", action="store_true", help="with --audio, keep the mp4 too")
    parser.add_argument("--quality", default="best", help="best, or a height such as 720")
    parser.add_argument("--card", action="store_true", help="render a shareable card png, download nothing")
    args = parser.parse_args()

    tid = post_id(args.link)
    post = fetch(tid)
    if post.get("__typename") == "TweetTombstone":
        raise SystemExit(f"post {tid} is not available publicly (deleted, protected or restricted)")

    describe(post, tid)
    if args.info:
        return

    if args.card:
        args.out.mkdir(parents=True, exist_ok=True)
        print(f"  card     {make_card(post, tid, args.out)}")
        return

    found = streams(post)
    if not found:
        raise SystemExit(f"post {tid} has no video stream (it may be text or photos only)")

    chosen = found[0]
    if args.quality != "best":
        wanted = args.quality.rstrip("p")
        match = [v for v in found if resolution(v) == f"{wanted}p"]
        if not match:
            raise SystemExit(f"no {wanted}p stream; available: "
                             + ", ".join(resolution(v) for v in found))
        chosen = match[0]

    user = (post.get("user") or {}).get("screen_name", "unknown")
    args.out.mkdir(parents=True, exist_ok=True)
    video = args.out / f"{user}_{tid}_{resolution(chosen)}.mp4"

    print(f"  saving   {video.name}  ({chosen['bitrate'] // 1000} kbps)")
    download(chosen["url"], video)
    print(f"  saved    {video}  ({video.stat().st_size / 1_048_576:.1f} MB)")

    if args.audio:
        audio = to_mp3(video, args.out / f"{user}_{tid}.mp3")
        print(f"  saved    {audio}  ({audio.stat().st_size / 1_048_576:.1f} MB)")
        if not args.keep_video:
            video.unlink()
            print("  removed  the mp4 (pass --keep-video to keep both)")



# ---------------------------------------------------------------- share card

CARD_W, CARD_H = 1080, 1350


def _wrap(text: str, per_line: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > per_line and line:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def _grab(url: str, path: pathlib.Path) -> bool:
    if not url:
        return False
    try:
        request = urllib.request.Request(url, headers={"user-agent": UA})
        with urllib.request.urlopen(request, timeout=30) as response:
            path.write_bytes(response.read())
        return True
    except Exception:
        return False


def make_card(post: dict, tid: str, out_dir: pathlib.Path) -> pathlib.Path:
    """Render our own card for the post: author, text and thumbnail."""
    from xml.sax.saxutils import escape

    user = post.get("user") or {}
    name = escape(user.get("name") or "unknown")
    handle = escape(user.get("screen_name") or "unknown")
    when = escape((post.get("created_at") or "")[:10])
    body = (post.get("text") or "").strip()

    media = (post.get("mediaDetails") or [{}])[0]
    thumb_url = media.get("media_url_https") or ""
    avatar_url = user.get("profile_image_url_https") or ""
    if avatar_url.endswith("_normal.jpg"):
        avatar_url = avatar_url.replace("_normal.jpg", "_200x200.jpg")

    work = out_dir / f".{tid}"
    work.mkdir(parents=True, exist_ok=True)
    thumb = work / "thumb.jpg"
    avatar = work / "avatar.jpg"
    has_thumb = bool(thumb_url) and _grab(thumb_url, thumb)
    has_avatar = _grab(avatar_url, avatar)

    lines = _wrap(body, 42)[:9]
    y = 700 if has_thumb else 470
    text_nodes = "\n".join(
        f'<text x="72" y="{y + i * 62}" class="body">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )

    clips = ""
    if has_thumb:
        clips += '<clipPath id="thumbClip"><rect x="72" y="230" width="936" height="420" rx="24"/></clipPath>'
    if has_avatar:
        clips += '<clipPath id="avatarClip"><circle cx="120" cy="132" r="44"/></clipPath>'

    # <image> must live in the body: elements inside <defs> are only declared.
    thumb_svg = ""
    if has_thumb:
        thumb_svg = (f'<image xlink:href="file://{thumb.resolve()}" href="file://{thumb.resolve()}" '
                     f'x="72" y="230" width="936" height="420" '
                     f'preserveAspectRatio="xMidYMid slice" clip-path="url(#thumbClip)"/>')

    avatar_svg = ""
    if has_avatar:
        avatar_svg = (f'<image xlink:href="file://{avatar.resolve()}" href="file://{avatar.resolve()}" '
                      f'x="76" y="88" width="88" height="88" clip-path="url(#avatarClip)"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{CARD_W}" height="{CARD_H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111315"/><stop offset="1" stop-color="#1b1f23"/>
    </linearGradient>
    {clips}
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  {thumb_svg}
  {avatar_svg}
  <text x="188" y="126" class="name">{name}</text>
  <text x="188" y="166" class="handle">@{handle} · {when}</text>
  {text_nodes}
  <line x1="72" y1="{CARD_H - 150}" x2="{CARD_W - 72}" y2="{CARD_H - 150}" stroke="#2c3238" stroke-width="1"/>
  <text x="72" y="{CARD_H - 104}" class="foot">x.com/{handle}/status/{tid}</text>
  <text x="72" y="{CARD_H - 64}" class="foot dim">Archived with x-archive</text>
  <style>
    .name   {{ font-family: sans-serif; font-size: 40px; font-weight: 700; fill: #f3f5f7; }}
    .handle {{ font-family: sans-serif; font-size: 28px; fill: #8b949e; }}
    .body   {{ font-family: sans-serif; font-size: 44px; fill: #e6edf3; }}
    .foot   {{ font-family: monospace; font-size: 24px; fill: #6e7781; }}
    .dim    {{ fill: #4d545c; }}
  </style>
</svg>'''

    svg_path = work / "card.svg"
    svg_path.write_text(svg)
    png_path = out_dir / f"{handle}_{tid}_card.png"
    result = subprocess.run(["rsvg-convert", "-o", str(png_path), str(svg_path)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"card rendering failed: {result.stderr.strip()[:200]}")
    return png_path


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\ninterrupted")
