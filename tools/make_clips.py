#!/usr/bin/env python3
"""Cut the Date Everything! voice lines out of the "All Voice Lines" videos.

You give it a folder with the audio of the videos (one file per video, with
the YouTube video id somewhere in the file name). It reads clips/cutlist.csv
and writes one short, levelled MP3 per voice line.

Needs Python 3.8+ and ffmpeg. No other installs.

Examples:
    python3 tools/make_clips.py downloads
    python3 tools/make_clips.py downloads --only dishy,hector
    python3 tools/make_clips.py downloads --out my_clips --shift 0.05
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CUTLIST = os.path.join(HERE, "..", "clips", "cutlist.csv")

GAP_BETWEEN_PARTS = 0.55   # seconds of silence between two speakers in a duo clip
HEAD_SILENCE = 0.10        # seconds of silence before the line
TAIL_SILENCE = 0.15        # seconds of silence after the line
TARGET_LUFS = -14.0        # loudness target, about the level of a phone notification
TRUE_PEAK = -1.5


def run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-2000:])
        raise SystemExit("ffmpeg failed: " + " ".join(cmd[:6]) + " ...")
    return result


def find_source(folder, video_id):
    for name in sorted(os.listdir(folder)):
        if video_id in name and not name.startswith("."):
            return os.path.join(folder, name)
    return None


def cut_part(src, start, end, shift, out_wav):
    start = max(0.0, start + shift)
    length = max(0.05, end - start + shift)
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", src,
        "-ac", "1", "-ar", "48000",
        "-af", (
            "highpass=f=90,"
            "acompressor=threshold=-26dB:ratio=3:attack=5:release=150,"
            "afade=t=in:d=0.004,"
            f"areverse,afade=t=in:d=0.012,areverse"
        ),
        out_wav,
    ])


def join_parts(parts, out_wav):
    inputs = []
    chain = []
    for i, p in enumerate(parts):
        inputs += ["-i", p]
        chain.append(f"[{i}:a]")
        if i < len(parts) - 1:
            chain.append(f"[gap{i}]")
    gaps = "".join(
        f"aevalsrc=0:d={GAP_BETWEEN_PARTS}:s=48000[gap{i}];" for i in range(len(parts) - 1)
    )
    n = len(chain)
    graph = (
        gaps
        + "".join(chain)
        + f"concat=n={n}:v=0:a=1,"
        + f"adelay={int(HEAD_SILENCE * 1000)},apad=pad_dur={TAIL_SILENCE}[out]"
    )
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-ar", "48000", out_wav])


def level_to_mp3(src_wav, out_mp3):
    first = f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json"
    measured = run(["ffmpeg", "-hide_banner", "-y", "-i", src_wav, "-af", first, "-f", "null", "-"])
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", measured.stderr, re.S)
    if match:
        m = json.loads(match.group(0))
        second = (
            f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true"
        )
    else:
        second = f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src_wav,
         "-af", second, "-ac", "1", "-ar", "48000",
         "-c:a", "libmp3lame", "-b:a", "192k", out_mp3])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio_folder", help="folder with the downloaded audio of the videos")
    ap.add_argument("--out", default="date_everything", help="where to write the clips (default: date_everything)")
    ap.add_argument("--only", default="", help="comma-separated characters, e.g. dishy,lux (default: all)")
    ap.add_argument("--cutlist", default=DEFAULT_CUTLIST, help="path to cutlist.csv")
    ap.add_argument("--shift", type=float, default=0.0,
                    help="move every cut by this many seconds if your copy is slightly offset (e.g. 0.05 or -0.05)")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is not installed. See the README for how to get it.")
    if not os.path.isdir(args.audio_folder):
        raise SystemExit(f"Folder not found: {args.audio_folder}")

    only = {c.strip().lower() for c in args.only.split(",") if c.strip()}
    clips = OrderedDict()
    with open(args.cutlist, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if only and row["character"].lower() not in only:
                continue
            clips.setdefault(row["file"], []).append(row)
    if not clips:
        raise SystemExit("Nothing to cut. Check --only.")

    missing = sorted({r["video_id"] for rows in clips.values() for r in rows
                      if not find_source(args.audio_folder, r["video_id"])})
    if missing:
        print("Can't find audio for these video ids in", args.audio_folder)
        for vid in missing:
            print(f"  https://youtu.be/{vid}")
        raise SystemExit("Name each file with its video id (yt-dlp does this with -o \"%(id)s.%(ext)s\").")

    os.makedirs(args.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for n, (name, rows) in enumerate(clips.items(), 1):
            parts = []
            for i, r in enumerate(rows):
                part = os.path.join(tmp, f"part{i}.wav")
                cut_part(find_source(args.audio_folder, r["video_id"]),
                         float(r["start"]), float(r["end"]), args.shift, part)
                parts.append(part)
            joined = os.path.join(tmp, "joined.wav")
            join_parts(parts, joined)
            level_to_mp3(joined, os.path.join(args.out, name))
            print(f"[{n}/{len(clips)}] {name}")

    print(f"\nDone. {len(clips)} clips are in: {os.path.abspath(args.out)}")
    print("Next: upload them to Home Assistant (Media > My media > date_everything).")


if __name__ == "__main__":
    main()
