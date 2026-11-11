"""Comfy Recipe's own ComfyUI: detect hardware, install with uv, start/stop it. Stdlib only, no Hermes imports.

The install runs as a DETACHED background process (``python installer.py run <dir>``) so it survives the chat turn and
Hermes restarts; it reports through ``<dir>/.comfy-recipe/status.json`` + ``install.log``. The plugin only ever starts
or stops the ComfyUI inside this folder (pid recorded in ``server.json`` and checked against its command line).

Layout of an install folder (default <Documents>/ComfyRecipeEnv):
    ComfyUI/                 ComfyUI source (git clone of the latest release tag, or the release zip without git)
    venv/                    Python 3.13 made by uv, PyTorch for this machine's GPU, ComfyUI + ComfyUI-Manager deps
    comfyui.log              server log
    .comfy-recipe/           manifest.json (port, gpu, torch build), status.json, install.log, server.json
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib import request

REPO = "https://github.com/Comfy-Org/ComfyUI"
PYTHON_VERSION = "3.13"
# Official upstream release checksums, reviewed with the plugin's pinned source.
# https://github.com/astral-sh/uv/releases/download/0.13.7/sha256.sum
UV_VERSION = "0.13.7"
UV_SHA256 = {
    "uv-aarch64-apple-darwin.tar.gz": "81b811b57e4624df7ed3aac148e0359100d9962f3d9dce00aec533dc2e086731",
    "uv-aarch64-pc-windows-msvc.zip": "505d9e65e7692bac3ddf98c66754aa26c5050c409c184af30a881a0a72cc85e3",
    "uv-aarch64-unknown-linux-gnu.tar.gz": "71279f8d3c67241e807b9d8db872d1bf541579fb9f08b7d1eb1682196d1e57dc",
    "uv-x86_64-apple-darwin.tar.gz": "20c47e4c1f630b8abaff8c291fa9b9aa300fef92c4fbff95adf198b55287cda7",
    "uv-x86_64-pc-windows-msvc.zip": "0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021",
    "uv-x86_64-unknown-linux-gnu.tar.gz": "c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83",
}
PORT_RANGE = range(8190, 8200)
DOWNLOAD_GB = 6      # PyTorch CUDA wheels dominate
DISK_NEEDED_GB = 15  # install + uv cache + room for a first model
IS_WIN = os.name == "nt"
STEPS = ["Get the uv installer", "Download Python " + PYTHON_VERSION, "Download ComfyUI",
         "Install PyTorch for your GPU (largest download)", "Install ComfyUI and ComfyUI-Manager",
         "Link shared models", "Check the GPU works"]
# Rough share of the total install time per step (sums to 100): drives the desktop progress bar.
STEP_WEIGHTS = [2, 4, 8, 55, 22, 2, 7]
CARD = {"kind": "install", "title": "Installing ComfyUI", "steps": STEPS, "weights": STEP_WEIGHTS}


def progress_card(d) -> str:
    """MEDIA line of the install progress card (the installer's own status.json)."""
    return "MEDIA:" + str(_meta(Path(d).expanduser()) / "status.json")


def install_identity(previous: dict | None = None) -> dict:
    """New installations opt into onboarding; a retry keeps its stable identity."""
    import uuid
    previous = previous or {}
    return {'install_id': previous.get('install_id') or str(uuid.uuid4()),
            'onboarding_version': previous.get('onboarding_version', 1)}


def documents_dir() -> Path:
    """The user's real Documents folder (Windows known folder - may be redirected, e.g. to OneDrive; XDG on Linux)."""
    if IS_WIN:
        try:
            import ctypes
            import uuid
            guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}").bytes_le)
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path and Path(path).is_dir():
                    return Path(path)
        except Exception:
            pass
    elif shutil.which("xdg-user-dir"):
        try:
            r = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() and Path(r.stdout.strip()) != Path.home():
                return Path(r.stdout.strip())
        except Exception:
            pass
    docs = Path.home() / "Documents"
    return docs if docs.is_dir() else Path.home()


def default_dir() -> Path:
    return documents_dir() / "ComfyRecipeEnv"


SYNC_MARKERS = {"onedrive": "OneDrive", "mobile documents": "iCloud Drive", "icloud": "iCloud Drive",
                "cloudstorage": "a cloud drive", "dropbox": "Dropbox", "google drive": "Google Drive", "my drive": "Google Drive"}


def synced_by(path) -> str | None:
    """Name of the cloud-sync service whose folder contains ``path`` (a 15 GB install there would be uploaded)."""
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError:
        pass
    for part in p.parts:
        low = part.lower()
        for key, name in SYNC_MARKERS.items():
            if low == key or low.startswith(key + " ") or low.startswith(key + "-"):
                return name
    return None


def check_dir(path) -> dict:
    """Is ``path`` usable as an install folder? Never creates anything."""
    p = Path(os.path.expandvars(str(path))).expanduser()
    info = {"path": str(p), "absolute": p.is_absolute()}
    if not p.is_absolute():
        return info | {"ok": False, "problem": "give a full folder path, e.g. " + str(default_dir())}
    probe = p
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = round(shutil.disk_usage(probe).free / 2**30, 1) if probe.exists() else 0
    writable = probe.exists() and os.access(probe, os.W_OK)
    ours = bool(manifest(p)) or (_meta(p) / "status.json").exists()
    foreign = (p / "ComfyUI").exists() and not ours
    nonempty = p.is_dir() and any(c.name != ".comfy-recipe" for c in p.iterdir()) and not ours
    info.update(free_gb=free, writable=writable, synced_by=synced_by(p), existing_comfy_recipe_install=ours)
    problems = []
    if not probe.exists():
        problems.append(f"the drive {p.anchor or p} does not exist")
    elif not writable:
        problems.append(f"cannot write to {probe}")
    if free < DISK_NEEDED_GB:
        problems.append(f"only {free} GB free there, about {DISK_NEEDED_GB} GB needed")
    if foreign:
        problems.append("that folder already contains a ComfyUI that Comfy Recipe did not make - choose another folder")
    elif nonempty:
        problems.append("that folder is not empty - choose a new or empty folder (Comfy Recipe creates it)")
    info["ok"] = not problems
    if problems:
        info["problem"] = "; ".join(problems)
    return info


def _meta(d: Path) -> Path:
    return Path(d) / ".comfy-recipe"


def _read(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def manifest(d) -> dict | None:
    return _read(_meta(d) / "manifest.json")


def _clean_env() -> dict:
    """Hermes injects PYTHONPATH etc.; ComfyUI's venv must not see them."""
    drop = {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONSTARTUP"}
    env = {k: v for k, v in os.environ.items() if k.upper() not in drop}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=_clean_env(), **kw)


# ---------------------------------------------------------------- hardware detection
def detect_gpus() -> dict:
    """{'kind': nvidia|apple|amd|cpu, 'gpus': [{index, name, vram_gb}], 'torch_index': url|None, 'note': str}"""
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            r = _run([smi, "--query-gpu=index,name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"],
                     timeout=15)
            gpus, drivers, caps = [], [], []
            for ln in r.stdout.splitlines():
                parts = [x.strip() for x in ln.split(",")]
                if len(parts) >= 3 and parts[0].isdigit():
                    gpus.append({"index": int(parts[0]), "name": parts[1], "vram_gb": round(float(parts[2]) / 1024, 1)})
                    drivers.append(float(re.sub(r"[^\d.]", "", parts[3]) or 0) if len(parts) > 3 else 0)
                    caps.append(float(parts[4]) if len(parts) > 4 and re.match(r"^[\d.]+$", parts[4]) else 0)
            if gpus:
                driver, cap = min(drivers), min(c for c in caps) if caps else 0
                if cap and cap < 7.5:  # 10-series and older: newest CUDA builds dropped them
                    cu, note = "cu126", "older NVIDIA GPU: PyTorch CUDA 12.6 build"
                elif driver >= 580:
                    cu, note = "cu130", "PyTorch CUDA 13.0 build (ComfyUI's recommendation)"
                elif driver >= 570:
                    cu, note = "cu128", "driver older than 580: PyTorch CUDA 12.8 build (updating the NVIDIA driver is recommended)"
                else:
                    cu, note = "cu126", "old NVIDIA driver: PyTorch CUDA 12.6 build (updating the driver is recommended)"
                return {"kind": "nvidia", "gpus": gpus, "driver": driver,
                        "torch_index": f"https://download.pytorch.org/whl/{cu}", "note": note}
        except Exception:
            pass
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return {"kind": "apple", "gpus": [{"index": 0, "name": "Apple Silicon (Metal)", "vram_gb": None}],
                "torch_index": None, "note": "Apple Silicon: standard PyTorch with Metal (MPS)"}
    if sys.platform.startswith("linux") and (shutil.which("rocminfo") or Path("/opt/rocm").exists()):
        return {"kind": "amd", "gpus": [{"index": 0, "name": "AMD GPU (ROCm)", "vram_gb": None}],
                "torch_index": "https://download.pytorch.org/whl/rocm7.2", "note": "AMD on Linux: PyTorch ROCm 7.2 build"}
    return {"kind": "cpu", "gpus": [], "torch_index": "https://download.pytorch.org/whl/cpu",
            "note": "No supported GPU found automatically: ComfyUI will run on the CPU (very slow - fine to explore, "
                    "not to generate). AMD/Intel GPUs on Windows need a manual PyTorch setup."}


def free_port() -> int:
    for p in PORT_RANGE:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"no free port in {PORT_RANGE.start}-{PORT_RANGE.stop - 1}")


def disk_free_gb(d) -> float:
    p = Path(d)
    while not p.exists() and p.parent != p:
        p = p.parent
    return round(shutil.disk_usage(p).free / 2**30, 1)


def model_dirs_of(root) -> list[str]:
    """Model folders an existing ComfyUI uses (for display): its models/ + folders named in extra_model_paths.yaml."""
    root = Path(root)
    out = [str(root / "models")] if (root / "models").is_dir() else []
    y = root / "extra_model_paths.yaml"
    if y.exists():
        for ln in y.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip().split(": ", 1)[-1].strip()
            if re.match(r"^([A-Za-z]:[\\/]|/)", ln) and Path(ln).is_dir():
                q = Path(ln)
                out.append(str(q.parent if q.parent.name.lower() == "models" else q))
    return list(dict.fromkeys(out))


def running_comfy_roots() -> list[str]:
    """ComfyUI folders of ComfyUI servers running right now (any launcher, any port): a process running main.py from a
    folder that has comfy/model_management.py. Finds portable installs no config file points at."""
    try:
        import psutil
    except ImportError:
        return []
    roots = []
    for proc in psutil.process_iter(["name", "cmdline", "cwd"]):
        try:
            cmd = proc.info.get("cmdline") or []
            if not cmd or "python" not in (proc.info.get("name") or "").lower():
                continue
            mp = next((c for c in cmd if c.replace("\\", "/").lower().endswith("main.py")), None)
            if not mp:
                continue
            root = Path(mp) if Path(mp).is_absolute() else Path(proc.info.get("cwd") or "") / mp
            root = root.parent
            if (root / "comfy" / "model_management.py").exists():
                roots.append(str(root.resolve()))
        except Exception:
            continue
    return list(dict.fromkeys(roots))


# ---------------------------------------------------------------- uv
def find_uv(tools_dir: Path | None = None) -> str | None:
    cands = [shutil.which("uv")]
    exe = "uv.exe" if IS_WIN else "uv"
    for base in filter(None, [os.environ.get("HERMES_HOME"), (Path(os.environ["LOCALAPPDATA"]) / "hermes") if IS_WIN and os.environ.get("LOCALAPPDATA") else None,
                              Path.home() / ".hermes", Path.home() / ".local"]):
        cands.append(str(Path(base) / "bin" / exe))
    cands.append(str(Path.home() / ".cargo" / "bin" / exe))
    if tools_dir:
        cands.append(str(Path(tools_dir) / exe))
    return next((c for c in cands if c and Path(c).exists()), None)


def _download_uv(tools_dir: Path, log) -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        arch = "aarch64"
    elif m in ("amd64", "x86_64"):
        arch = "x86_64"
    else:
        raise RuntimeError(f"Unsupported uv bootstrap architecture: {m}; install uv from its official source")
    if IS_WIN:
        name = f"uv-{arch}-pc-windows-msvc.zip"
    elif sys.platform == "darwin":
        name = f"uv-{arch}-apple-darwin.tar.gz"
    elif sys.platform.startswith("linux"):
        name = f"uv-{arch}-unknown-linux-gnu.tar.gz"
    else:
        raise RuntimeError(f"Unsupported uv bootstrap platform: {sys.platform}")
    expected = UV_SHA256[name]
    url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{name}"
    log(f"downloading {url}")
    tools_dir.mkdir(parents=True, exist_ok=True)
    exe = "uv.exe" if IS_WIN else "uv"
    target = tools_dir / exe
    # Never extract archive paths or links. Only the verified release's expected executable
    # is copied to a fixed filename, atomically, so failed downloads cannot leave runnable code.
    with tempfile.TemporaryDirectory(dir=tools_dir) as td:
        arc = Path(td) / name
        request.urlretrieve(url, arc)
        with arc.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise RuntimeError(f"uv checksum mismatch for {name}: expected {expected}, got {actual}")
        staged = Path(td) / exe
        if name.endswith(".zip"):
            with zipfile.ZipFile(arc) as z:
                hits = [i for i in z.infolist() if i.filename == exe and not i.is_dir()]
                if len(hits) != 1:
                    raise RuntimeError("uv archive must contain exactly one regular file " + exe)
                with z.open(hits[0]) as source, staged.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        else:
            import tarfile
            with tarfile.open(arc) as t:
                member_name = name.removesuffix(".tar.gz") + "/uv"
                hits = [i for i in t.getmembers() if i.name == member_name]
                if len(hits) != 1 or not hits[0].isfile():
                    raise RuntimeError("uv archive must contain exactly one regular file " + member_name)
                with t.extractfile(hits[0]) as source, staged.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        staged.replace(target)
    if not IS_WIN:
        target.chmod(0o755)
    return str(target)


# ---------------------------------------------------------------- install (runs detached)
def _latest_tag(log) -> str | None:
    git = shutil.which("git")
    try:
        if git:
            r = _run([git, "ls-remote", "--tags", "--refs", REPO + ".git"], timeout=60)
            tags = re.findall(r"refs/tags/(v\d+\.\d+\.\d+)$", r.stdout, re.M)
        else:
            with request.urlopen("https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest", timeout=30) as f:
                tags = [json.loads(f.read())["tag_name"]]
        return max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else None
    except Exception as e:
        log(f"could not read the latest release tag ({e}); using the default branch")
        return None


def _vpy(d: Path) -> Path:
    return d / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")


def install(d: Path, port: int, gpu: int | None, share_from: list[str] | None) -> None:
    d = Path(d)
    meta = _meta(d)
    meta.mkdir(parents=True, exist_ok=True)
    logf = (meta / "install.log").open("a", encoding="utf-8")
    status = {**CARD, "state": "running", "pid": os.getpid(), "dir": str(d), "step": 0, "step_name": STEPS[0],
              "started_at": time.time(), "updated_at": time.time(), "log": str(meta / "install.log")}

    def log(msg: str) -> None:
        logf.write(time.strftime("[%H:%M:%S] ") + msg.rstrip() + "\n")
        logf.flush()

    def step(i: int) -> None:
        status.update(step=i, step_name=STEPS[i], updated_at=time.time())
        status.setdefault("step_times", {})[STEPS[i]] = time.time()
        _write(meta / "status.json", status)
        log(f"== step {i + 1}/{len(STEPS)}: {STEPS[i]}")

    def sh(cmd, timeout=3600, cwd=None) -> str:
        log("$ " + " ".join(str(c) for c in cmd))
        p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", env=_clean_env() | {"UV_NO_PROGRESS": "1"}, cwd=cwd)
        out = []
        t0 = time.time()
        for ln in p.stdout:
            out.append(ln)
            log(ln)
            if time.time() - t0 > timeout:
                p.kill()
                raise RuntimeError(f"timed out after {timeout}s: {cmd[0]}")
        if p.wait() != 0:
            raise RuntimeError(f"command failed ({p.returncode}): {' '.join(str(c) for c in cmd[:4])} ... - "
                               + "".join(out[-6:]).strip()[-800:])
        return "".join(out)

    try:
        hw = detect_gpus()
        log(f"hardware: {json.dumps(hw)}  port={port} gpu={gpu} share_from={share_from}")
        step(0)
        uv = find_uv(meta / "tools") or _download_uv(meta / "tools", log)
        log("uv: " + uv)
        step(1)
        sh([uv, "python", "install", PYTHON_VERSION])
        if not _vpy(d).exists():
            sh([uv, "venv", "--python", PYTHON_VERSION, d / "venv"])
        step(2)
        src = d / "ComfyUI"
        if not (src / "main.py").exists():
            tag = _latest_tag(log)
            git = shutil.which("git")
            if git:
                sh([git, "clone", "--depth", "1"] + (["--branch", tag] if tag else []) + [REPO + ".git", src], timeout=1200)
            else:
                url = f"{REPO}/archive/refs/tags/{tag}.zip" if tag else f"{REPO}/archive/refs/heads/master.zip"
                log("downloading " + url)
                with tempfile.TemporaryDirectory() as td:
                    z = Path(td) / "comfyui.zip"
                    request.urlretrieve(url, z)
                    with zipfile.ZipFile(z) as zf:
                        zf.extractall(td)
                    inner = next(p for p in Path(td).iterdir() if p.is_dir())
                    shutil.move(str(inner), str(src))
            status["comfyui_version"] = tag
        step(3)
        torch = ["torch", "torchvision", "torchaudio"]
        idx = ["--index-url", hw["torch_index"]] if hw.get("torch_index") else []
        sh([uv, "pip", "install", "--python", _vpy(d)] + torch + idx, timeout=7200)
        step(4)
        sh([uv, "pip", "install", "--python", _vpy(d), "-r", src / "requirements.txt"], timeout=3600)
        if (src / "manager_requirements.txt").exists():
            sh([uv, "pip", "install", "--python", _vpy(d), "-r", src / "manager_requirements.txt"], timeout=1800)
        step(5)
        if share_from:  # on the NEW venv's Python: it has PyYAML (a ComfyUI requirement); the host Python may not
            sh([_vpy(d), Path(__file__).resolve(), "share", src] + [a for r in share_from for a in ("--share", r)], timeout=300)
            log("extra_model_paths.yaml written for: " + ", ".join(share_from))
        else:
            log("no shared models")
        step(6)
        check = sh([_vpy(d), "-c", "import torch,json;print(json.dumps({'torch':torch.__version__,'cuda':torch.cuda.is_available(),"
                    "'devices':[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],"
                    "'mps':getattr(torch.backends,'mps',None) is not None and torch.backends.mps.is_available()}))"], timeout=600)
        tc = json.loads(check.strip().splitlines()[-1])
        if hw["kind"] == "nvidia" and not tc["cuda"]:
            raise RuntimeError("PyTorch was installed but cannot see the NVIDIA GPU (update the NVIDIA driver, then reinstall)")
        _write(meta / "manifest.json", {**install_identity(manifest(d)), "version": 1, "dir": str(d), "comfyui_dir": str(src), "python": str(_vpy(d)),
                                        "port": port, "gpu": gpu, "hardware": hw["kind"], "torch": tc,
                                        "comfyui_version": status.get("comfyui_version"), "shared_models": share_from or [],
                                        "installed_at": time.time()})
        status.update(state="done", step=len(STEPS), step_name="Done", updated_at=time.time(),
                      duration_s=round(time.time() - status["started_at"]), torch=tc)
        _write(meta / "status.json", status)
        log(f"DONE in {status['duration_s']}s: {tc}")
    except Exception as e:
        status.update(state="error", error=f"{type(e).__name__}: {e}", updated_at=time.time())
        _write(meta / "status.json", status)
        log(f"ERROR: {status['error']}")
    finally:
        logf.close()


def write_shared_models(comfy_dir: Path, roots: list[str]) -> Path:
    """Let the new ComfyUI use the models of other ComfyUI installs (nothing copied). ``roots`` are ComfyUI root folders.
    Each root gives its own models/ folder (standard type names) plus the sections of its extra_model_paths.yaml
    (e.g. StabilityMatrix's shared Data/Models mapping), with is_default removed - so new downloads always land in
    this install's own models/ folder."""
    import yaml  # run through `installer.py share` on the ComfyUI venv's Python, which has PyYAML
    doc: dict = {}
    for i, root in enumerate(roots, 1):
        r = Path(root)
        models = r / "models"
        if models.is_dir():
            sec = {"base_path": models.as_posix()}
            sec.update({c.name: c.name for c in sorted(models.iterdir()) if c.is_dir() and c.name != "configs"})
            doc[f"shared_{i}_{r.name}_models"] = sec
        y = r / "extra_model_paths.yaml"
        if y.exists():
            try:
                src = yaml.safe_load(y.read_text(encoding="utf-8", errors="replace")) or {}
            except Exception:
                src = {}
            for name, sec in src.items():
                if not isinstance(sec, dict):
                    continue
                sec = {k: v for k, v in sec.items() if k != "is_default"}
                bp = sec.get("base_path")
                if bp and not Path(os.path.expandvars(str(bp))).expanduser().is_absolute():
                    sec["base_path"] = (r / str(bp)).resolve().as_posix()
                doc[f"shared_{i}_{name}"] = sec
    p = Path(comfy_dir) / "extra_model_paths.yaml"
    head = ("# Written by Comfy Recipe: models shared from other ComfyUI installs (nothing is copied).\n"
            "# New downloads go to this install's own models/ folder. Delete this file to stop sharing.\n")
    p.write_text(head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    return p


def spawn_install(d, port: int, gpu: int | None, share_from: list[str] | None) -> dict:
    d = Path(d).expanduser()
    meta = _meta(d)
    st = install_status(d)
    if st.get("state") == "running" and st.get("alive"):
        return st
    meta.mkdir(parents=True, exist_ok=True)
    _write(meta / "status.json", {**CARD, "state": "running", "dir": str(d), "step": 0, "step_name": "starting",
                                  "started_at": time.time(), "updated_at": time.time(), "log": str(meta / "install.log")})
    args = [_host_python(), str(Path(__file__).resolve()), "run", str(d), "--port", str(port)]
    if gpu is not None:
        args += ["--gpu", str(gpu)]
    for s in share_from or []:
        args += ["--share", s]
    p = _detached(args, meta / "installer.out", cwd=str(d))
    st = _read(meta / "status.json", {})
    st["pid"] = p.pid
    _write(meta / "status.json", st)
    return install_status(d)


def _host_python() -> str:
    exe = Path(sys.executable)
    if exe.stem.lower().startswith("python"):
        return str(exe)
    for name in ("python.exe" if IS_WIN else "python3", "python"):
        c = exe.parent / name
        if c.exists():
            return str(c)
    return shutil.which("python3") or shutil.which("python") or str(exe)


def _detached(args, out_path: Path, cwd: str):
    with open(out_path, "ab") as out:
        kw = dict(stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=cwd, env=_clean_env(), close_fds=True)
        if IS_WIN:
            base = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            try:  # survive the Hermes process (its job object) when allowed
                return subprocess.Popen(args, creationflags=base | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
            except OSError:
                return subprocess.Popen(args, creationflags=base, **kw)
        return subprocess.Popen(args, start_new_session=True, **kw)


def _pid_alive(pid, must_contain: str | None = None) -> bool:
    if not pid:
        return False
    try:
        import psutil
        p = psutil.Process(int(pid))
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return False
        if must_contain:
            return must_contain.lower() in " ".join(p.cmdline()).replace("\\", "/").lower()
        return True
    except ImportError:
        if IS_WIN:
            r = _run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], timeout=10)
            return str(pid) in r.stdout
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False
    except Exception:
        return False


def install_status(d, tail: int = 8) -> dict:
    meta = _meta(Path(d).expanduser())
    st = _read(meta / "status.json", {}) or {}
    if not st:
        return {"state": "none"}
    if st.get("state") == "running":
        st["alive"] = _pid_alive(st.get("pid"))
        if not st["alive"] and time.time() - st.get("updated_at", 0) > 20:
            st.update(state="error", error="the installer process stopped unexpectedly - see the log")
    log = meta / "install.log"
    if log.exists():
        lines = [ln for ln in log.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        st["log_tail"] = [ln[-200:] for ln in lines[-tail:]]
    st["elapsed_s"] = round(time.time() - st.get("started_at", time.time()))
    st["step_of"] = f"{min(st.get('step', 0) + 1, len(STEPS))}/{len(STEPS)}"
    st["progress_card"] = progress_card(d)
    return st


def wait_status(d, wait_s: int = 0) -> dict:
    """Block until the step changes, the install ends or wait_s passes - lets the agent report each finished step."""
    st = install_status(d)
    deadline = time.time() + max(0, min(int(wait_s or 0), 900))
    while st.get("state") == "running" and time.time() < deadline:
        time.sleep(3)
        nxt = install_status(d)
        if nxt.get("step") != st.get("step") or nxt.get("state") != "running":
            return nxt
        st = nxt
    return st


# ---------------------------------------------------------------- server start / stop
def _url(m: dict) -> str:
    return f"http://127.0.0.1:{m['port']}"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.3):
            return True
    except OSError:
        return False


def _http_ok(url: str) -> bool:
    try:
        with request.urlopen(url + "/system_stats", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def server_running(d) -> bool:
    m = manifest(d)
    return bool(m) and _port_open(m["port"]) and _http_ok(_url(m))


MANAGER_RESTART = "[ComfyUI-Manager] Restarting"  # Manager re-execs main.py after installing node-pack dependencies


def listener_pid(port: int, marker: str) -> int | None:
    """PID of Comfy Recipe's ComfyUI serving `port`: the outermost process whose command line lives in the install
    folder (`marker`). On Windows the venv python.exe is a launcher whose child (the base interpreter) owns the socket,
    and the listening socket is not always reported as LISTEN - so take any local socket on the port and walk up."""
    try:
        import psutil
        owners = {c.pid for c in psutil.net_connections(kind="tcp") if c.laddr and c.laddr.port == int(port) and c.pid}
        for pid in owners:
            proc, found = psutil.Process(pid), None
            while proc is not None:
                if marker.lower() in " ".join(proc.cmdline()).replace("\\", "/").lower():
                    found = proc.pid
                elif found:
                    break
                proc = proc.parent()
            if found:
                return found
    except Exception:
        return None
    return None


def start(d, wait_s: int = 180) -> dict:
    d = Path(d).expanduser()
    m = manifest(d)
    if not m:
        raise RuntimeError(f"no finished Comfy Recipe install in {d}")
    url = _url(m)
    if server_running(d):
        return {"started": False, "running": True, "url": url, "note": "already running"}
    if _port_open(m["port"]):
        raise RuntimeError(f"port {m['port']} is used by another program; change 'port' in {_meta(d) / 'manifest.json'}")
    args = [m["python"], "main.py", "--port", str(m["port"]), "--enable-manager", "--preview-method", "auto"]
    if m.get("gpu") is not None:
        args += ["--cuda-device", str(m["gpu"])]
    log = d / "comfyui.log"
    if log.exists() and log.stat().st_size > 20 * 2**20:
        os.replace(log, d / "comfyui.prev.log")
    p = _detached(args, log, cwd=m["comfyui_dir"])
    _write(_meta(d) / "server.json", {"pid": p.pid, "started_at": time.time(), "args": args})
    t0, size0, relaunched = time.time(), log.stat().st_size if log.exists() else 0, False
    marker = d.resolve().as_posix()
    while time.time() - t0 < wait_s:
        if _http_ok(url):
            res = {"started": True, "running": True, "url": url, "seconds": round(time.time() - t0, 1)}
            if relaunched:  # record the re-executed process, or a later stop() would miss it
                pid = listener_pid(m["port"], marker)
                if pid:
                    _write(_meta(d) / "server.json", {"pid": pid, "started_at": time.time(), "args": args})
                res["note"] = "ComfyUI-Manager restarted ComfyUI once to apply node-pack dependencies"
            return res
        if not relaunched and p.poll() is not None:
            with open(log, "rb") as f:
                f.seek(size0)
                new_log = f.read().decode("utf-8", errors="replace")
            if MANAGER_RESTART not in new_log:
                raise RuntimeError("ComfyUI exited while starting:\n" + "\n".join(new_log.splitlines()[-15:]))
            relaunched = True  # the replacement process keeps writing to the same log and opens the same port
        time.sleep(1.5)
    return {"started": True, "running": False, "url": url, "note": f"still starting after {wait_s}s - call start again"}


def stop(d, port: int | None = None) -> dict:
    """Stop Comfy Recipe's ComfyUI of folder `d`. `port` = fallback when the folder (and its manifest) is gone but the
    old process still runs; only a process whose command line lives in `d` is ever stopped."""
    d = Path(d).expanduser()
    srv = _read(_meta(d) / "server.json", {}) or {}
    pid = srv.get("pid")
    marker = Path(d).resolve().as_posix()  # the venv python in the command line lives inside the install folder
    if not _pid_alive(pid, marker):
        m = manifest(d)  # e.g. ComfyUI-Manager re-executed ComfyUI under a new PID, or the folder was deleted
        port = (m or {}).get("port") or port
        pid = listener_pid(port, marker) if port else None
        if not pid:
            return {"stopped": False, "note": "not running (no live process started by Comfy Recipe)"}
    try:
        import psutil
        proc = psutil.Process(int(pid))
        if marker.lower() not in " ".join(proc.cmdline()).replace("\\", "/").lower():
            return {"stopped": False, "note": f"pid {pid} is not Comfy Recipe's ComfyUI - left alone"}
        for c in proc.children(recursive=True):
            c.terminate()
        proc.terminate()
        psutil.wait_procs([proc], timeout=15)
    except ImportError:
        if IS_WIN:
            _run(["taskkill", "/PID", str(pid), "/T", "/F"], timeout=30)
        else:
            os.kill(int(pid), 15)
    return {"stopped": True, "pid": pid}


# ---------------------------------------------------------------- stop together with Hermes
# ComfyUI is launched detached (breakaway from Hermes' job object) and the plugin itself usually lives in the background
# gateway process, which keeps running after the desktop window closes. So a small watchdog process watches the Hermes
# process(es) the user actually closes and stops ComfyUI when all of them are gone.
WATCH_POLL_S = 3.0
WATCH_IDLE_EXIT_S = 90  # ComfyUI not running this long (stopped elsewhere; Manager restarts take ~30 s) -> watchdog exits


def hermes_owner_pids() -> list[int]:
    """The Hermes processes whose exit should stop ComfyUI: the desktop app's main process(es) when it runs,
    otherwise this process (CLI / gateway-only use)."""
    try:
        import psutil
        owners = [p.info["pid"] for p in psutil.process_iter(["pid", "name", "cmdline"])
                  if (p.info["name"] or "").lower() in ("hermes.exe", "hermes")
                  and not any(str(a).startswith("--type=") for a in (p.info["cmdline"] or []))]  # Electron helpers
        return owners or [os.getpid()]
    except Exception:
        return [os.getpid()]


def ensure_watchdog(d, owners: list[int]) -> dict:
    """Record the owners and make sure exactly one watchdog runs for install `d`."""
    d = Path(d).expanduser()
    meta = _meta(d)
    _write(meta / "owners.json", {"pids": sorted(set(int(p) for p in owners)), "updated_at": time.time()})
    w = _read(meta / "watchdog.json", {}) or {}
    if _pid_alive(w.get("pid"), "installer.py watch " + d.resolve().as_posix()):
        return {"watchdog": w["pid"], "owners": sorted(set(owners)), "new": False}
    p = _detached([_host_python(), str(Path(__file__).resolve()), "watch", str(d)], meta / "watchdog.out", cwd=str(d))
    _write(meta / "watchdog.json", {"pid": p.pid, "started_at": time.time()})
    return {"watchdog": p.pid, "owners": sorted(set(owners)), "new": True}


def release_watchdog(d) -> None:
    """stop_with_hermes switched off: the watchdog exits at its next poll, ComfyUI keeps running."""
    meta = _meta(Path(d).expanduser())
    if (meta / "watchdog.json").exists():
        _write(meta / "owners.json", {"pids": [], "keep_running": True, "updated_at": time.time()})


def _comfy_running(d: Path, m: dict) -> bool:
    marker = d.resolve().as_posix()
    srv = _read(_meta(d) / "server.json", {}) or {}
    return _pid_alive(srv.get("pid"), marker) or bool(listener_pid(m["port"], marker))


def watch(d, poll: float = WATCH_POLL_S, idle_exit_s: float = WATCH_IDLE_EXIT_S, max_loops: int | None = None) -> str:
    d = Path(d).expanduser()
    idle_since, loops = None, 0
    while max_loops is None or loops < max_loops:
        loops += 1
        time.sleep(poll)
        m = manifest(d)
        if not m:
            return "install gone"
        owners = _read(_meta(d) / "owners.json", {}) or {}
        if owners.get("keep_running"):
            return "keep running (stop_with_hermes off)"
        if not _comfy_running(d, m):
            idle_since = idle_since or time.time()
            if time.time() - idle_since > idle_exit_s:
                return "ComfyUI not running"
            continue
        idle_since = None
        pids = owners.get("pids") or []
        if pids and not any(_pid_alive(p) for p in pids):
            fresh = (_read(_meta(d) / "owners.json", {}) or {}).get("pids") or []  # a new session may have just registered
            if not any(_pid_alive(p) for p in fresh):
                stop(d)
                return "Hermes closed: ComfyUI stopped"
    return "max loops"


def adopt(d, timeout: int = 240) -> dict:
    """Take back an existing Comfy Recipe install (after a reset, or after the user MOVED the folder).
    Rewrites the manifest's absolute paths when the folder moved, then proves the venv runs ComfyUI's Python deps."""
    d = Path(os.path.expandvars(str(d))).expanduser()
    if not d.is_absolute():
        raise ValueError("give the full folder path of the Comfy Recipe install")
    m = manifest(d)
    if not m:
        raise ValueError(f"{d} is not a Comfy Recipe install (no .comfy-recipe/manifest.json). If the folder was deleted, "
                         "make a new install instead.")
    d = d.resolve()
    old = Path(m.get("dir") or d)
    moved = str(old).lower() != str(d).lower()
    if moved:
        def rebase(v):
            try:
                return str(d / Path(v).relative_to(old))
            except ValueError:
                return v  # outside the old folder (e.g. shared model roots): unchanged
        _write(_meta(d) / "manifest.moved-from.json", m)
        m = dict(m, dir=str(d), comfyui_dir=rebase(m["comfyui_dir"]), python=rebase(m["python"]), moved_from=str(old))
        _write(_meta(d) / "manifest.json", m)
        _write(_meta(d) / "server.json", {})  # the old PID belongs to the old location
    problems = []
    if not Path(m["python"]).exists():
        problems.append(f"Python not found at {m['python']}")
    if not (Path(m["comfyui_dir"]) / "main.py").exists():
        problems.append(f"ComfyUI not found in {m['comfyui_dir']}")
    torch_v = None
    if not problems:
        r = _run([m["python"], "-c", "import torch, sys; print(torch.__version__, torch.cuda.is_available())"],
                 timeout=timeout, cwd=m["comfyui_dir"])
        if r.returncode != 0:
            problems.append("its Python environment does not start: " + (r.stderr or r.stdout).strip()[-400:])
        else:
            torch_v = r.stdout.strip()
    if problems:
        raise RuntimeError("cannot use this install: " + "; ".join(problems)
                           + ". A venv moved to another drive or broken by the move needs a new install.")
    return {"adopted": True, "dir": str(d), "moved_from": str(old) if moved else None, "port": m["port"],
            "gpu": m.get("gpu"), "torch": torch_v}


if __name__ == "__main__":
    # python installer.py run <install dir> --port N [--gpu N] [--share ROOT ...]   (host Python, stdlib only)
    # python installer.py share <ComfyUI dir> --share ROOT [...]                    (ComfyUI venv Python, needs PyYAML)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "share", "watch"])
    ap.add_argument("dir")
    ap.add_argument("--port", type=int)
    ap.add_argument("--gpu", type=int)
    ap.add_argument("--share", action="append")
    a = ap.parse_args()
    if a.cmd == "share":
        print(write_shared_models(Path(a.dir), a.share or []))
    elif a.cmd == "watch":
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "watching", a.dir, "pid", os.getpid(), flush=True)
        outcome = watch(Path(a.dir))
        print(time.strftime("%Y-%m-%d %H:%M:%S"), outcome, flush=True)
    else:
        install(Path(a.dir), a.port, a.gpu, a.share)
