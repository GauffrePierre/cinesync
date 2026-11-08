"""Lectures en cours du tableau de bord Plex : débit et décisions de transcodage."""

from app.routers.admin import _session, _totals

DIRECT = {
    "type": "movie", "title": "Dune", "year": 2021, "duration": 9_000_000, "viewOffset": 4_500_000, "thumb": "/library/metadata/1/thumb",
    "User": {"title": "Alex"}, "Player": {"title": "Salon", "platform": "Android", "state": "playing", "local": True},
    "Session": {"id": "a", "bandwidth": 21000, "location": "lan"},
    "Media": [{"bitrate": 20500, "videoResolution": "4k", "selected": True, "Part": [{"decision": "directplay"}]}],
}
TRANSCODE = {
    "type": "episode", "grandparentTitle": "Andor", "title": "Rix Road", "parentIndex": 1, "index": 12, "duration": 3_000_000, "viewOffset": 600_000,
    "User": {"title": "Sam"}, "Player": {"title": "iPhone", "platform": "iOS", "state": "paused", "local": False},
    "Session": {"id": "b", "bandwidth": 8200, "location": "wan"},
    "Media": [{"bitrate": 12000, "videoResolution": "1080", "Part": [{}]}],
    "TranscodeSession": {"videoDecision": "transcode", "audioDecision": "copy", "transcodeHwRequested": True, "speed": "2.4",
                         "throttled": False, "sourceVideoCodec": "hevc", "videoCodec": "h264"},
}


def test_direct_play_session():
    s = _session(DIRECT)
    assert s["transcode"] == "direct" and s["video"] == "direct" and s["audio"] == "direct"
    assert s["bandwidth_mbps"] == 21.0 and s["source_mbps"] == 20.5 and s["quality"] == "4K"
    assert s["local"] and s["progress"] == 50 and s["transcoding"] is None


def test_transcoding_session_and_totals():
    s = _session(TRANSCODE)
    assert s["transcode"] == "transcode" and s["video"] == "transcode" and s["audio"] == "copy"
    assert s["quality"] == "1080p" and s["bandwidth_mbps"] == 8.2 and not s["local"]
    assert s["transcoding"] == {"active": True, "hardware": True, "speed": 2.4, "throttled": False, "video_codec": "HEVC → H264"}
    assert s["detail"] == "S01E12 · Rix Road"
    assert _totals([_session(DIRECT), s]) == {"streams": 2, "transcodes": 1, "bandwidth_mbps": 29.2, "remote_mbps": 8.2}
