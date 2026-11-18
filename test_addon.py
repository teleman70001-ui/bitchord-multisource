"""Self-check: no frameworks, plain asserts. Run: python3 test_addon.py"""
import server as s


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# duration parsing
check(s.duration_to_seconds("3:35") == 215, "mm:ss")
check(s.duration_to_seconds("1:02:03") == 3723, "h:mm:ss")
check(s.duration_to_seconds("215.37") == 215, "float seconds")
check(s.duration_to_seconds(None) is None, "missing length")

# manifest contract (addon docs: id required, quality picker best-first)
check(s.MANIFEST["id"], "manifest id")
check("search" in s.MANIFEST["resources"], "search resource declared")
check(s.MANIFEST.get("bitchordAuth") is True, "bitchordAuth flag clears the Outdated addon note")
opts = s.MANIFEST["settings"][0]["options"]
check(opts[0]["value"] == "lossless", "best quality listed first")
check(len(opts) >= 2, "picker needs >=2 options")

# audio file selection
files = [
    {"name": "01 - Song.flac", "format": "Flac", "length": "215.3"},
    {"name": "01 - Song_vbr.mp3", "format": "VBR MP3", "length": "215.3"},
    {"name": "01 - Song_128kb.mp3", "format": "128Kbps MP3", "length": "215.3"},
    {"name": "art.jpg", "format": "JPEG"},
]
check(s._audio_files(files, "lossless")[0]["name"] == "01 - Song.flac", "lossless pick")
check(s._audio_files(files, "low")[0]["format"] == "128Kbps MP3", "low pick")
check(s._audio_files(files, "high")[0]["format"] == "VBR MP3", "high pick")

# routing
check(s.resolve("unknown:1", "lossless") is None, "unknown provider -> None")
check(s.archive_stream("archive:definitely-not-an-item-xyz:nope.flac", "lossless") is None, "missing item -> None")

# title cleanup
check(s._clean_query('the "best" of: (now)') == "the best of now", "query cleaned")

print("self-check ok")
