"""Video/image preparation for ComfyUI inputs (comfy_media tool).

Everything runs through ffmpeg/ffprobe on PATH. Outputs are written NEXT TO THE SOURCE file (never over it) and
every output is probed back before it is reported. An explicit `out`/`out_dir` must stay inside the source file's
folder, the plugin data folder or the ComfyUI instance's input/ or output/ folder. Existing files are never
overwritten: ffmpeg renders to a temporary sibling that is moved into place only when the target does not exist
(a default output name gets a _1, _2 ... suffix instead; an explicit `out` that exists is refused). `to_input=True` also copies the result into the ComfyUI
instance's `input/` folder, reusing a byte-identical file that is already there and never overwriting an
unrelated file with the same name.

Actions
- probe   : size, fps, frame count, duration, codecs, audio
- convert : one pass of trim (start/duration/end) + resize (width/height, mode cover|fit|stretch) + fps
- frames  : extract stills (first, last, frame index N, or time t) as PNG
- split   : cut into consecutive segments of `seconds` (re-encoded, frame-accurate)
- join    : concatenate clips (normalised to the first clip's size/fps; audio kept when every clip has it)
- sheet   : tiled contact sheet of N evenly spaced frames (for a quick visual check)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from contextvars import ContextVar
from fractions import Fraction
from pathlib import Path

VIDEO_ARGS = ["-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _bins() -> tuple[str, str]:
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not (ff and fp):
        raise RuntimeError("ffmpeg/ffprobe not found on PATH - install ffmpeg to prepare media")
    return ff, fp


def _env() -> dict:
    try:
        from .installer import child_env
    except ImportError:  # pragma: no cover - loaded outside the package
        from installer import child_env  # type: ignore
    return child_env()


def _run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=_env())
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(r.stderr or '').strip()[-800:]}")


def _num(s: str | None) -> str:
    """Compact number for file names: 3.0 -> '3', 2.5 -> '2.5'."""
    return ("%g" % float(s)) if s not in (None, "") else ""


def probe(path: str | Path) -> dict:
    _, fp = _bins()
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    r = subprocess.run([fp, "-v", "error", "-count_packets", "-show_entries",
                        "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_read_packets:format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=_env())
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr.strip()[-400:]}")
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    info = {"path": str(p), "bytes": p.stat().st_size, "has_audio": bool(a),
            "duration_s": round(float(d.get("format", {}).get("duration") or 0), 3)}
    if v:
        fps = float(Fraction(v.get("r_frame_rate") or "0/1")) if v.get("r_frame_rate") not in (None, "0/0") else 0.0
        info.update(width=v.get("width"), height=v.get("height"), fps=round(fps, 3), video_codec=v.get("codec_name"),
                    frames=int(v["nb_read_packets"]) if str(v.get("nb_read_packets", "")).isdigit() else None)
    if a:
        info["audio_codec"] = a.get("codec_name")
    return info


# Extra folders an explicit out/out_dir may point into besides the source file's folder: a list of paths or a
# zero-argument callable returning one (evaluated only when needed). handle() passes the plugin data folder and the
# instance's input/ and output/ folders; direct calls allow the source folder only.
_ROOTS: ContextVar = ContextVar("comfy_media_roots", default=())


def _allowed_roots(src: Path, roots) -> list[Path]:
    extra = roots() if callable(roots) else (roots or [])
    return [src.parent.resolve()] + [Path(r).resolve() for r in extra]


def _place(src: Path, out: str | Path | None, default: Path, roots=None) -> Path:
    """Final output path. out (relative = next to the source) must stay inside an allowed folder and must not
    exist; the default name moves to a free _1, _2 ... sibling instead."""
    explicit = bool(out)
    o = Path(out) if explicit else Path(default)
    o = (o if o.is_absolute() else src.parent / o).resolve()
    if o == src.resolve():
        raise ValueError("output would overwrite the source file")
    if not o.is_relative_to(src.parent.resolve()):
        allowed = _allowed_roots(src, _ROOTS.get() if roots is None else roots)
        if not any(o.is_relative_to(r) for r in allowed):
            raise ValueError(f"output {o} is outside the allowed folders (the source file's folder, the plugin data "
                             f"folder, the ComfyUI input/ or output/ folder)")
    if o.exists():
        if explicit:
            raise FileExistsError(f"{o} already exists - choose another output name (existing files are never "
                                  "overwritten)")
        k = 1
        while o.with_name(f"{o.stem}_{k}{o.suffix}").exists():
            k += 1
        o = o.with_name(f"{o.stem}_{k}{o.suffix}")
    o.parent.mkdir(parents=True, exist_ok=True)
    return o


def _out(src: Path, suffix: str, ext: str | None = None, out: str | None = None, roots=None) -> Path:
    return _place(src, out, src.with_name(f"{src.stem}_{suffix}{ext or src.suffix}"), roots)


def _commit(tmp: Path, target: Path) -> None:
    """Move tmp to target only if target does not exist (atomic on both platforms)."""
    try:
        if os.name == "nt":
            os.rename(tmp, target)  # raises FileExistsError instead of replacing
        else:
            os.link(tmp, target)  # raises FileExistsError instead of replacing
            tmp.unlink()
    except FileExistsError:
        tmp.unlink(missing_ok=True)
        raise FileExistsError(f"{target} appeared while rendering - not overwritten") from None


def _render(args: list[str], o: Path) -> None:
    """Run ffmpeg into a fresh temporary sibling of o (-n: never overwrite), then move it into place."""
    tmp = o.with_name(f".{o.stem}.{uuid.uuid4().hex[:8]}.part{o.suffix}")
    try:
        _run(args + ["-n", str(tmp)])
        _commit(tmp, o)
    finally:
        tmp.unlink(missing_ok=True)


def _scale_filter(width: int | None, height: int | None, mode: str) -> list[str]:
    if not (width or height):
        return []
    if not (width and height):  # one side given: keep aspect, even dimensions
        return [f"scale={width or -2}:{height or -2}:flags=lanczos"]
    if mode == "stretch":
        return [f"scale={width}:{height}:flags=lanczos", "setsar=1"]
    if mode == "fit":
        return [f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", "setsar=1"]
    return [f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos", f"crop={width}:{height}",
            "setsar=1"]


def convert(path: str, start: float | None = None, duration: float | None = None, end: float | None = None,
            width: int | None = None, height: int | None = None, fps: float | None = None, mode: str = "cover",
            out: str | None = None, _default: Path | None = None) -> dict:
    ff, _ = _bins()
    src = Path(path)
    info = probe(src)
    if end is not None and duration is None:
        duration = float(end) - float(start or 0)
    if duration is not None and duration <= 0:
        raise ValueError("duration must be > 0")
    filters = ([f"fps={fps}"] if fps else []) + _scale_filter(width, height, mode)
    parts = []
    if width or height:
        parts.append(f"{width or 'auto'}x{height or 'auto'}" + ("" if mode == "cover" else f"_{mode}"))
    if fps:
        parts.append(f"{_num(fps)}fps")
    if start or duration:
        s = float(start or 0)
        parts.append(f"{_num(s)}-{_num(s + duration) if duration else 'end'}s")
    if not parts:
        raise ValueError("convert needs at least one of start/duration/end, width/height, fps")
    if src.suffix.lower() in IMAGE_EXTS:
        if start or duration or fps:
            raise ValueError("a still image can only be resized (width/height/mode)")
        if Path(out or "x.png").suffix.lower() not in IMAGE_EXTS:
            raise ValueError(f"image output must keep an image extension, not {Path(out).suffix!r}")
        o = _out(src, "_".join(parts), src.suffix.lower(), out)
        _render([ff, "-v", "error", "-i", str(src), "-vf", ",".join(filters), "-frames:v", "1", "-update", "1"], o)
        return {"action": "convert", "source": info, "output": probe(o)}
    o = _place(src, out, _default) if _default is not None else _out(src, "_".join(parts), ".mp4", out)
    args = [ff, "-v", "error"] + (["-ss", str(start)] if start else []) + ["-i", str(src)]
    args += (["-t", str(duration)] if duration else []) + (["-vf", ",".join(filters)] if filters else [])
    args += VIDEO_ARGS + (AUDIO_ARGS if info["has_audio"] else ["-an"])
    _render(args, o)
    return {"action": "convert", "source": info, "output": probe(o)}


def frames(path: str, which: list | str = ("first", "last"), out_dir: str | None = None) -> dict:
    """which: 'first', 'last', an int frame index, or 't=<seconds>' (string)."""
    ff, _ = _bins()
    src = Path(path)
    info = probe(src)
    n = info.get("frames") or 0
    items = [which] if isinstance(which, (str, int)) else list(which)
    outs = []
    for w in items:
        if w == "first":
            sel, tag = "eq(n\\,0)", "first"
        elif w == "last":
            if not n:
                raise RuntimeError("frame count unknown - cannot locate the last frame")
            sel, tag = f"eq(n\\,{n - 1})", "last"
        elif isinstance(w, str) and w.startswith("t="):
            sel, tag = None, f"t{_num(w[2:])}s"
        else:
            idx = int(w)
            if n and not 0 <= idx < n:
                raise ValueError(f"frame {idx} out of range 0..{n - 1}")
            sel, tag = f"eq(n\\,{idx})", f"f{idx}"
        name = f"{src.stem}_{tag}.png"
        o = _place(src, None, (Path(out_dir) / name) if out_dir else src.with_name(name))
        if sel:
            args = [ff, "-v", "error", "-i", str(src), "-vf", f"select={sel}", "-fps_mode", "passthrough",
                    "-frames:v", "1", "-update", "1"]
        else:
            args = [ff, "-v", "error", "-ss", w[2:], "-i", str(src), "-frames:v", "1", "-update", "1"]
        _render(args, o)
        if not o.is_file() or o.stat().st_size == 0:
            raise RuntimeError(f"no frame written for {w!r}")
        outs.append({"which": w, "path": str(o), "width": info.get("width"), "height": info.get("height")})
    return {"action": "frames", "source": info, "outputs": outs}


def split(path: str, seconds: float, out_dir: str | None = None, chained: bool = False,
          width: int | None = None, height: int | None = None, fps: float | None = None, mode: str = "cover") -> dict:
    """Consecutive segments. chained=True adds one frame so segment k+1 starts on segment k's LAST frame
    (generate k+1 from k's last output frame, then join with drop_first=1). width/height/fps/mode as in convert."""
    src = Path(path)
    info = probe(src)
    total = info["duration_s"]
    if seconds <= 0:
        raise ValueError("seconds must be > 0")
    rate = float(fps or info["fps"] or 24)
    extra = (1.0 / rate) if chained else 0.0
    outs, s, k = [], 0.0, 1
    while s < total - 0.05:
        d = min(seconds + extra, total - s)
        name = f"{src.stem}_seg{k:02d}_{_num(round(s, 3))}-{_num(round(s + d, 3))}s.mp4"
        o = (Path(out_dir) / name) if out_dir else src.with_name(name)
        outs.append(convert(str(src), start=s or None, duration=d, width=width, height=height, fps=fps,
                            mode=mode, _default=o)["output"])
        s += seconds
        k += 1
    return {"action": "split", "source": info, "chained": chained, "outputs": outs}


def join(paths: list[str], out: str | None = None, drop_first: int = 0) -> dict:
    """drop_first=N removes the first N frames of every clip after the first (chained segments repeat the
    previous segment's last frame as their first frame: drop_first=1)."""
    ff, _ = _bins()
    if len(paths) < 2:
        raise ValueError("join needs at least two clips")
    infos = [probe(p) for p in paths]
    ref = infos[0]
    w, h, fps = ref["width"], ref["height"], ref["fps"] or 24
    audio = all(i["has_audio"] for i in infos)
    first = Path(paths[0])
    o = _out(first, "joined", ".mp4", out)
    args = [ff, "-v", "error"]
    for p in paths:
        args += ["-i", str(p)]
    chains, labels = [], ""
    drop_first = max(0, int(drop_first or 0))
    for k in range(len(paths)):
        cut = drop_first if k else 0
        vtrim = f"trim=start_frame={cut},setpts=PTS-STARTPTS," if cut else ""
        atrim = f"atrim=start={cut / fps:.6f},asetpts=PTS-STARTPTS," if cut else ""
        chains.append(f"[{k}:v]fps={fps},{vtrim}scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                      f"crop={w}:{h},setsar=1,format=yuv420p[v{k}]")
        if audio:
            chains.append(f"[{k}:a]{atrim}aresample=48000,aformat=channel_layouts=stereo[a{k}]")
        labels += f"[v{k}]" + (f"[a{k}]" if audio else "")
    fc = ";".join(chains) + f";{labels}concat=n={len(paths)}:v=1:a={1 if audio else 0}[v]" + ("[a]" if audio else "")
    args += ["-filter_complex", fc, "-map", "[v]"] + (["-map", "[a]"] if audio else [])
    args += VIDEO_ARGS + (AUDIO_ARGS if audio else ["-an"])
    _render(args, o)
    res = {"action": "join", "inputs": infos, "drop_first": drop_first, "output": probe(o)}
    if not audio and any(i["has_audio"] for i in infos):
        res["warning"] = "some clips had no audio track - output has no audio"
    return res


def mux(path: str, audio: str, out: str | None = None, music_volume: float | None = None,
        fade_out: float = 0.5) -> dict:
    """Put a sound/music track on a video. The video stream is copied untouched. When the video already has
    sound, the new track is MIXED UNDER it (music_volume, default 0.5); otherwise it becomes the soundtrack
    (default 1.0). The track is trimmed (with a short fade-out) or padded with silence to the video length."""
    ff, _ = _bins()
    src, track = Path(path), Path(audio)
    info, ainfo = probe(src), probe(track)
    if not info.get("width"):
        raise ValueError("mux needs a video as path")
    if not ainfo.get("has_audio"):
        raise ValueError("the audio file has no audio stream")
    dur = float(info["duration_s"] or 0)
    if dur <= 0:
        raise ValueError("video duration unknown")
    vol = float(music_volume if music_volume is not None else (0.5 if info["has_audio"] else 1.0))
    if not 0 <= vol <= 4:
        raise ValueError("music_volume must be between 0 and 4")
    fade = max(0.0, min(float(fade_out or 0), dur / 2))
    music = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol:g},apad,atrim=0:{dur:.3f}"
             + (f",afade=t=out:st={dur - fade:.3f}:d={fade:.3f}" if fade else "") + "[m]")
    if info["has_audio"]:
        fc = (f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur:.3f}[v];{music};"
              "[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    else:
        fc = music.replace("[m]", "[a]")
    o = _out(src, "with_sound", ".mp4", out)
    _render([ff, "-v", "error", "-i", str(src), "-i", str(track), "-filter_complex", fc,
             "-map", "0:v:0", "-map", "[a]", "-c:v", "copy"] + AUDIO_ARGS + ["-t", f"{dur:.3f}"], o)
    res = {"action": "mux", "source": info, "audio": ainfo, "mode": "mix" if info["has_audio"] else "soundtrack",
           "music_volume": vol, "output": probe(o)}
    if not res["output"].get("has_audio"):
        raise RuntimeError("mux output has no audio stream")
    return res


def sheet(path: str, count: int = 8, columns: int = 4, out: str | None = None) -> dict:
    ff, _ = _bins()
    src = Path(path)
    info = probe(src)
    dur = max(info["duration_s"], 0.04)
    rows = -(-count // columns)
    o = _out(src, "sheet", ".jpg", out)
    _render([ff, "-v", "error", "-i", str(src), "-vf", f"fps={count}/{dur},scale=270:-1,tile={columns}x{rows}",
             "-frames:v", "1", "-update", "1"], o)
    return {"action": "sheet", "source": info, "path": str(o),
            "layout": f"{columns}x{rows}, {count} frames evenly spaced over {dur:.2f}s (row-major)"}


def _md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to_input(path: str | Path, input_dir: str | Path) -> dict:
    """Copy into ComfyUI input/, reusing an identical file; never overwrite a different one."""
    src, dst_dir = Path(path), Path(input_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    digest = _md5(src)
    for f in dst_dir.iterdir():
        if f.is_file() and f.stat().st_size == src.stat().st_size and _md5(f) == digest:
            return {"input_name": f.name, "reused": True, "path": str(f)}
    dst, k = dst_dir / src.name, 1
    while dst.exists():
        dst = dst_dir / f"{src.stem}_{k}{src.suffix}"
        k += 1
    shutil.copy2(src, dst)
    if _md5(dst) != digest:
        raise RuntimeError(f"copy verification failed for {dst}")
    return {"input_name": dst.name, "reused": False, "path": str(dst)}


def _output_paths(res: dict) -> list[str]:
    if "output" in res:
        return [res["output"]["path"]]
    if "outputs" in res:
        return [o["path"] for o in res["outputs"]]
    return [res["path"]] if "path" in res else []


def handle(p: dict, input_dir_for=None, allowed_roots=None) -> dict:
    """allowed_roots: extra folders an explicit out/out_dir may use (list or zero-argument callable)."""
    a = p.get("action", "probe")
    if a == "probe":
        return probe(p["path"])
    token = _ROOTS.set(allowed_roots or ())
    try:
        res = _action(p, a)
    finally:
        _ROOTS.reset(token)
    return _finish(p, a, res, input_dir_for)


def _action(p: dict, a: str) -> dict:
    if a == "convert":
        res = convert(p["path"], p.get("start"), p.get("duration"), p.get("end"), p.get("width"), p.get("height"),
                      p.get("fps"), p.get("mode") or "cover", p.get("out"))
    elif a == "frames":
        res = frames(p["path"], p.get("which") or ["first", "last"], p.get("out_dir"))
    elif a == "split":
        res = split(p["path"], float(p["seconds"]), p.get("out_dir"), bool(p.get("chained")), p.get("width"),
                    p.get("height"), p.get("fps"), p.get("mode") or "cover")
    elif a == "join":
        res = join(p["paths"], p.get("out"), int(p.get("drop_first") or 0))
    elif a == "sheet":
        res = sheet(p["path"], int(p.get("count", 8)), int(p.get("columns", 4)), p.get("out"))
    elif a == "mux":
        res = mux(p["path"], p["audio"], p.get("out"), p.get("music_volume"),
                  0.5 if p.get("fade_out") is None else float(p["fade_out"]))
    else:
        raise ValueError(f"unknown action {a!r}")
    return res


def _finish(p: dict, a: str, res: dict, input_dir_for) -> dict:
    if p.get("to_input") and a != "sheet":
        if input_dir_for is None:
            raise RuntimeError("no ComfyUI instance to copy into")
        input_dir = input_dir_for(p.get("instance"))
        res["input_files"] = [copy_to_input(x, input_dir) for x in _output_paths(res)]
        res["next"] = ("The window's file pickers only list new input files after desktop_preview close + open; "
                       "then select input_name visibly in the Load Image / Load Video node.")
    return res
