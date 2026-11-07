# M3U Playlist Checker

A small, dependency-free Python script that reads an IPTV playlist (`.m3u` / `.m3u8`), tests every stream URL and tells you which ones are dead. It can also write a cleaned playlist with only the working streams, and a CSV report you can open in Excel or Google Sheets.

Useful when a playlist has thousands of channels and you want to know, before opening your TV app, how many of them actually answer.

Maintained by [SmartVPro](https://github.com/smartvpro-tv).

## Features

- Reads the playlist from a local file **or** a URL
- Parses `#EXTINF` attributes: channel name, `group-title`, `tvg-id`, `tvg-logo`; keeps `#EXTVLCOPT` lines
- Checks streams in parallel (thread pool), HEAD request first, GET fallback for servers that reject HEAD
- Prints status code and response time per stream, plus a summary and a dead-streams-by-group breakdown
- `--alive` writes a playlist of working streams, `--dead` a playlist of failed ones, `--csv` a report
- `--group` filters to one category before checking
- Python 3.8+, standard library only, nothing to install

## Install

```bash
git clone https://github.com/smartvpro-tv/m3u-playlist-checker.git
cd m3u-playlist-checker
```

That is all. No `pip install`.

## Usage

```bash
# check a local playlist
python m3u_checker.py playlist.m3u

# check a playlist URL with 20 parallel requests and an 8 second timeout
python m3u_checker.py "https://example.com/get.php?username=U&password=P&type=m3u_plus" --workers 20 --timeout 8

# write a report and a cleaned playlist
python m3u_checker.py playlist.m3u --csv report.csv --alive working.m3u --dead broken.m3u

# only check the "Sports" group, print just the summary
python m3u_checker.py playlist.m3u --group Sports --quiet
```

Example output:

```
Checking 1842 streams with 10 workers, 10s timeout...

[1/1842] OK       200    312 ms  BBC One HD
[2/1842] DEAD     404    120 ms  Old Channel
...

============================================================
Total:   1842
Working: 1701  (92%)
Dead:    141
Time:    94.3s

Dead streams by group:
     63  Movies VOD
     40  Regional
     ...
CSV report written to report.csv
Working playlist written to working.m3u
```

## Options

| Option | Default | Meaning |
|---|---|---|
| `source` | — | path or URL of the playlist |
| `--workers N` | 10 | parallel requests. 10–30 is reasonable; higher values may get you rate-limited by the server |
| `--timeout S` | 10 | seconds to wait per request |
| `--csv FILE` | — | write a CSV report (name, group, tvg_id, url, ok, status, ms, error) |
| `--alive FILE` | — | write a playlist with working streams only |
| `--dead FILE` | — | write a playlist with dead streams only |
| `--group NAME` | — | only check entries whose `group-title` contains NAME (case-insensitive) |
| `--quiet` | off | summary only |

## How "working" is decided

A stream counts as working when the server answers with an HTTP status in the 200–399 range. The script does not download or play the stream, so a stream can be "working" and still fail in a player (DRM, geo-blocking by the CDN, wrong codec). It is a fast first filter, not a playback test. For a playback test, open the `--alive` playlist in VLC.

## Limitations

- Some servers return 200 for every URL and only fail when playback starts. Nothing a HEAD/GET check can detect.
- Streams protected by referer/user-agent checks may report dead here but work in your app. Edit `USER_AGENT` at the top of the script if needed.
- Very large playlists (50 000+ entries) take a while. Use `--group` to split the work.

## Legal

This tool checks URLs you already have. It does not contain, generate or distribute any playlists, streams or channel lists. Only use it with playlists you are entitled to use.

## Related

- [iptv-toolkit](https://github.com/smartvpro-tv/iptv-toolkit): the full toolkit — check, clean, merge and filter playlists and test real stream speed ([docs](https://smartvpro-tv.github.io/iptv-toolkit/))
- [awesome-iptv-players](https://github.com/smartvpro-tv/awesome-iptv-players): which app to use on each device
- [iptv-setup-guides](https://github.com/smartvpro-tv/iptv-setup-guides): installation guides
- [iptv-troubleshooting](https://github.com/smartvpro-tv/iptv-troubleshooting): buffering, EPG and login fixes

## License

MIT. See [LICENSE](LICENSE).
