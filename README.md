# x-archive

Save a public X post's video, audio, or a shareable card — from a link, on your
own machine.

Built for the case where a post is worth keeping and X isn't a filing cabinet:
a tutorial you'll rewatch, a clip for a lesson, a thread you want as an image.

## What it does

```
x-archive <link>              download the highest-quality MP4
x-archive <link> --audio      convert to MP3 (highest quality, via ffmpeg)
x-archive <link> --card       render a shareable PNG card
x-archive <link> --info       show the post and every available stream
```

A link is `https://x.com/<user>/status/<id>`, `twitter.com` works too, and a bare
post id is accepted.

```
$ ./x_archive.py https://x.com/NASA/status/2105842656429432894 --info

  author   @NASA  (NASA)
  posted   2026-10-02T02:09:48.000Z
  text     Welcome aboard! After nearly eight hours in flight, Crew-13 arrived…
  streams  4
     10368000 bps    1080p  10368 kbps
      2176000 bps     720p   2176 kbps
       832000 bps     360p    832 kbps
       288000 bps     270p    288 kbps
```

The download is the highest bitrate stream X stores — 1080p at ~10 Mbps in the
example above, i.e. the original upload, not a re-encode.

## How it works

Public posts can be read through the same endpoint X uses to render embedded
posts (`cdn.syndication.twimg.com/tweet-result`). That returns the author, the
text, and every media variant with its bitrate and dimensions. We pick the
highest, or the height you ask for, and stream it from X's CDN. Nothing is
proxied, re-hosted or re-encoded — your machine talks to X directly.

`--card` renders **our own** layout from that public metadata (author, avatar,
thumbnail, text) with SVG and `rsvg-convert`. It is not a screenshot of X's UI,
and it keeps the source link and attribution on the card.

## Requirements

- Python 3.10+ (standard library only)
- `ffmpeg` for `--audio`
- `rsvg-convert` for `--card`

## What it will not do

- Private, protected, deleted or sensitive posts — these return a tombstone and
  are reported as unavailable, not worked around.
- Rate-limit evasion, account cookies, or anything behind a login.
- Bulk crawling.

It is a personal archival tool for public posts. The media belongs to its
author: keep the attribution on the card, and don't redistribute other people's
work as your own. Use it the way you'd use a bookmark folder.

## Roadmap

- [x] resolve a post and list its streams
- [x] download best MP4, convert to MP3
- [x] render a shareable card
- [ ] archive a whole thread
- [x] organise saved posts by topic from their text — in the Android app, from a
      small keyword table plus hashtags
- [x] the same thing inside Pocket, triggered from the share sheet — the Rust
      worker resolves and downloads on the device, with resumable transfers

The Android side lives in the `pocket-media` branch of the challenge repository; this
repository stays the command-line tool.
