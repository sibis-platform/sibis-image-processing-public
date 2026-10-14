#!/usr/bin/env python3
"""
Build a patched SIF on top of an existing, already-built base SIF.

A patch replaces specific files inside the base image. Each patch lives in
patches/<name>/ with a manifest.json (format in PATCHES.md). The base is never
rebuilt: the patched image bootstraps from the exact base SIF, so the result
is the base plus the listed file replacements and nothing else.

Examples:
  bin/patch-sif.py --base <base.sif> --list
  bin/patch-sif.py --base <base.sif> --patch atropos251 --patch qatoolsfix
  bin/patch-sif.py --interactive
"""

import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PATCHES_DIR = REPO / "patches"
DEFAULT_IMAGES_DIR = REPO / "build"
IMAGE_PATCH_DIR = "/opt/sibis-patches"
IMAGE_VERSIONS_JSON = "/usr/local/tools/VERSIONS.json"
APPTAINER = os.environ.get("APPTAINER", "apptainer")

# How to read each tool's version from a base that has no VERSIONS.json.
# Each snippet runs inside the base and prints a version string, or nothing.
PROBES = {
    "ants": "/usr/local/tools/ants/install/bin/antsRegistration --version 2>/dev/null"
            " | sed -n 's/^ANTs Version: *//p' | head -n1",
    "freesurfer": "grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' /usr/local/tools/freesurfer/build-stamp.txt"
                  " 2>/dev/null | head -n1",
}

OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}


class PatchError(Exception):
    pass


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path, show_progress=False):
    h = hashlib.sha256()
    size = os.path.getsize(path)
    done = 0
    last_pct = -1
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
            done += len(chunk)
            if show_progress and size:
                pct = done * 100 // size
                if pct // 10 != last_pct // 10:
                    print(f"  hashing {Path(path).name}: {pct}%", file=sys.stderr)
                    last_pct = pct
    return h.hexdigest()


# --------------------------------------------------------------------------- versions

def vtuple(s):
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", s or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def satisfies(version, spec):
    v = vtuple(version)
    if v is None:
        return False
    for clause in spec.split(","):
        clause = clause.strip()
        m = re.fullmatch(r"(>=|<=|==|!=|>|<)\s*(\S+)", clause)
        want = vtuple(m.group(2)) if m else None
        if want is None:
            raise PatchError(f"bad version requirement '{clause}'")
        n = max(len(v), len(want))
        a = v + (0,) * (n - len(v))
        b = want + (0,) * (n - len(want))
        if not OPS[m.group(1)](a, b):
            return False
    return True


# --------------------------------------------------------------------------- patches

def list_patch_names(patches_dir):
    if not patches_dir.is_dir():
        return []
    return sorted(p.name for p in patches_dir.iterdir() if (p / "manifest.json").is_file())


def load_patch(patches_dir, name):
    pdir = patches_dir / name
    mpath = pdir / "manifest.json"
    if not mpath.is_file():
        raise PatchError(f"no patch named '{name}' (expected {mpath})")
    raw = mpath.read_bytes()
    try:
        m = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PatchError(f"{mpath}: invalid JSON: {e}")
    for key in ("name", "tag", "requires", "files", "origin"):
        if key not in m:
            raise PatchError(f"{mpath}: missing '{key}'")
    if m["name"] != name:
        raise PatchError(f"{mpath}: name '{m['name']}' does not match its directory '{name}'")
    if not re.fullmatch(r"[a-z0-9]+", m["tag"]):
        raise PatchError(f"{mpath}: tag '{m['tag']}' must be lowercase letters and digits only")
    if not m["files"]:
        raise PatchError(f"{mpath}: 'files' is empty")
    staged_names = set()
    for f in m["files"]:
        for k in ("src", "replace", "sha256"):
            if k not in f:
                raise PatchError(f"{mpath}: a files entry is missing '{k}'")
        if not f["replace"].startswith("/"):
            raise PatchError(f"{mpath}: replace path must be absolute: {f['replace']}")
        src = pdir / f["src"]
        if not src.is_file():
            raise PatchError(f"{mpath}: source file not found: {src}")
        actual = sha256_file(src)
        if actual != f["sha256"]:
            raise PatchError(
                f"{src}: sha256 {actual} does not match manifest {f['sha256']}"
                " (if this file is in Git LFS, run `git lfs pull`)"
            )
        if src.name in staged_names:
            raise PatchError(f"{mpath}: two files share the name {src.name}")
        staged_names.add(src.name)
        f["_src_path"] = src
    if m.get("verify"):
        vpath = pdir / m["verify"]
        if not vpath.is_file():
            raise PatchError(f"{mpath}: verify script not found: {vpath}")
        m["_verify_path"] = vpath
    m["_dir"] = pdir
    m["_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    return m


# --------------------------------------------------------------------------- base image

def run_in_image(sif, script, capture=True):
    cmd = [APPTAINER, "exec", "--cleanenv", str(sif), "bash", "-c", script]
    return subprocess.run(cmd, capture_output=capture, text=True)


def probe_base(sif, replace_paths):
    lines = []
    for tool, snippet in PROBES.items():
        lines.append(f'echo "__probe {tool} $({snippet})"')
    lines.append(f'[ -f {IMAGE_VERSIONS_JSON} ] && echo "__versions_json $(base64 -w0 {IMAGE_VERSIONS_JSON})"')
    lines.append(f'[ -f {IMAGE_PATCH_DIR}/PATCHES.json ] && echo "__patches_json $(base64 -w0 {IMAGE_PATCH_DIR}/PATCHES.json)"')
    paths = sorted(replace_paths)
    for i, p in enumerate(paths):
        q = shlex.quote(p)
        lines.append(
            f'if [ -f {q} ]; then'
            f' echo "__target {i} $(sha256sum {q} | cut -d" " -f1) $([ -e {q}.orig ] && echo 1 || echo 0)";'
            f' else echo "__missing {i}"; fi'
        )
    lines.append("true")
    res = run_in_image(sif, "\n".join(lines))
    if res.returncode != 0:
        raise PatchError(f"could not inspect base image:\n{res.stderr.strip()}")

    info = {"versions": {}, "version_sources": {}, "patches": [], "targets": {}}
    for line in res.stdout.splitlines():
        if line.startswith("__probe "):
            parts = line.split(" ", 2)
            value = parts[2].strip() if len(parts) > 2 else ""
            if value:
                info["versions"][parts[1]] = value
                info["version_sources"][parts[1]] = "probe"
        elif line.startswith("__versions_json "):
            data = json.loads(base64.b64decode(line.split(" ", 1)[1]))
            for tool, value in data.items():
                info["versions"][tool] = str(value)
                info["version_sources"][tool] = IMAGE_VERSIONS_JSON
        elif line.startswith("__patches_json "):
            data = json.loads(base64.b64decode(line.split(" ", 1)[1]))
            info["patches"] = data.get("patches", [])
        elif line.startswith("__target "):
            _, idx, sha, has_orig = line.split()
            info["targets"][paths[int(idx)]] = {"sha256": sha, "orig_exists": has_orig == "1"}
        elif line.startswith("__missing "):
            info["targets"][paths[int(line.split()[1])]] = None
    return info


def eligibility(patch, info):
    reasons = []
    if patch["name"] in {p.get("name") for p in info["patches"]}:
        reasons.append("already applied to this base")
    for tool, spec in patch["requires"].items():
        version = info["versions"].get(tool)
        if not version:
            reasons.append(f"{tool} version unknown in base (add a probe or use --assume-version {tool}=X.Y.Z)")
        elif not satisfies(version, spec):
            reasons.append(f"{tool} {version} does not satisfy {spec}")
    for f in patch["files"]:
        t = info["targets"].get(f["replace"])
        if t is None:
            reasons.append(f"{f['replace']} not found in base")
        elif t["orig_exists"]:
            reasons.append(f"{f['replace']}.orig already exists in base")
        elif f.get("replaces_sha256") and t["sha256"] != f["replaces_sha256"]:
            reasons.append(
                f"{f['replace']} in base has sha256 {t['sha256']},"
                f" but this patch was written against {f['replaces_sha256']}"
            )
    return reasons


# --------------------------------------------------------------------------- build

def git_info():
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        status = subprocess.check_output(
            ["git", "-C", str(REPO), "status", "--porcelain", "--", "patches", "bin/patch-sif.py"],
            text=True, stderr=subprocess.DEVNULL).strip()
        return {"repo_commit": commit, "repo_dirty": bool(status)}
    except (OSError, subprocess.CalledProcessError):
        return {"repo_commit": None, "repo_dirty": None}


def output_name(base, patches):
    stem = base.name[:-4] if base.name.endswith(".sif") else base.name
    return f"{stem}+{'-'.join(p['tag'] for p in patches)}.sif"


def make_provenance(base, base_sha, info, patches, assumed, ts):
    entries = list(info["patches"])
    for p in patches:
        entries.append({
            "name": p["name"],
            "tag": p["tag"],
            "description": p.get("description", ""),
            "origin": p["origin"],
            "requested_by": p.get("requested_by", ""),
            "requires": p["requires"],
            "manifest_sha256": p["_manifest_sha256"],
            "applied_to": base.name,
            "applied_at": ts,
            "files": [
                {
                    "replace": f["replace"],
                    "sha256": f["sha256"],
                    "original_sha256": info["targets"][f["replace"]]["sha256"],
                    "original_kept_as": f["replace"] + ".orig",
                }
                for f in p["files"]
            ],
        })
    return {
        "schema": 1,
        "built_at": ts,
        "built_by": getpass.getuser(),
        "build_host": socket.gethostname(),
        "tool": git_info(),
        "base": {
            "sif": base.name,
            "path": str(base),
            "sha256": base_sha,
            "versions": info["versions"],
            "version_sources": info["version_sources"],
            "versions_assumed": assumed,
        },
        "patches": entries,
    }


def render_def(base, stage, provenance, patches):
    calls = []
    for p in patches:
        for f in p["files"]:
            calls.append(
                f"    replace_file {shlex.quote(p['name'])} {shlex.quote(f['_src_path'].name)}"
                f" {shlex.quote(f['replace'])} {f['sha256']}"
            )
    names = ",".join(e["name"] for e in provenance["patches"])
    commit = provenance["tool"]["repo_commit"] or "unknown"
    help_lines = "\n".join(f"    - {e['name']}: {e.get('description', '')}" for e in provenance["patches"])
    return f"""Bootstrap: localimage
From: {base}

%files
    {stage} {IMAGE_PATCH_DIR}.new

%post
    set -eu
    mkdir -p {IMAGE_PATCH_DIR}
    cp -a {IMAGE_PATCH_DIR}.new/. {IMAGE_PATCH_DIR}/
    rm -rf {IMAGE_PATCH_DIR}.new

    replace_file() {{
        src="{IMAGE_PATCH_DIR}/$1/$2"; t="$3"
        [ -f "$t" ] || {{ echo "patch $1: $t not found" >&2; exit 1; }}
        [ ! -e "$t.orig" ] || {{ echo "patch $1: $t.orig already exists" >&2; exit 1; }}
        cp -p "$t" "$t.orig"
        cp "$src" "$t"
        chmod --reference="$t.orig" "$t"
        chown --reference="$t.orig" "$t"
        echo "$4  $t" | sha256sum -c -
    }}

{chr(10).join(calls)}

%labels
    org.sibis.base_sif {base.name}
    org.sibis.base_sha256 {provenance['base']['sha256']}
    org.sibis.patches {names}
    org.sibis.patch_repo_commit {commit}
    org.sibis.patch_built {provenance['built_at']}

%help
    sibis-image-processing, patched.
    Base image: {base.name}
    Full provenance: {IMAGE_PATCH_DIR}/PATCHES.json
    Patches:
{help_lines}
"""


def verify_image(sif, patches):
    lines = ["set -e"]
    for p in patches:
        for f in p["files"]:
            lines.append(f"echo {shlex.quote(f['sha256'] + '  ' + f['replace'])} | sha256sum -c -")
        if p.get("_verify_path"):
            script = f"{IMAGE_PATCH_DIR}/{p['name']}/{p['_verify_path'].name}"
            lines.append(f"echo '--- verify {p['name']}'")
            lines.append(f"bash {shlex.quote(script)}")
    res = run_in_image(sif, "\n".join(lines), capture=False)
    return res.returncode == 0


def build(args, base, info, patches, assumed):
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / output_name(base, patches)
    work = out_dir / ("patchwork_" + out.name[:-4])
    if work.exists():
        shutil.rmtree(work)
    stage = work / "stage"
    stage.mkdir(parents=True)

    for p in patches:
        pstage = stage / p["name"]
        pstage.mkdir()
        shutil.copy2(p["_dir"] / "manifest.json", pstage / "manifest.json")
        for f in p["files"]:
            shutil.copy2(f["_src_path"], pstage / f["_src_path"].name)
        if p.get("_verify_path"):
            shutil.copy2(p["_verify_path"], pstage / p["_verify_path"].name)

    ts = now_utc()
    if args.dry_run:
        base_sha = "skipped (dry run)"
    else:
        print(f"Hashing base image for provenance (large files take a few minutes) ...", file=sys.stderr)
        base_sha = sha256_file(base, show_progress=True)
    provenance = make_provenance(base, base_sha, info, patches, assumed, ts)
    if provenance["tool"]["repo_dirty"]:
        print("warning: patches/ or bin/patch-sif.py has uncommitted changes;"
              " the recorded repo commit will not fully describe this build", file=sys.stderr)
    (stage / "PATCHES.json").write_text(json.dumps(provenance, indent=2) + "\n")
    deffile = work / "patch.def"
    deffile.write_text(render_def(base, stage, provenance, patches))

    if args.dry_run:
        print(f"Dry run: definition file and staged files are in {work}")
        print(f"Would build: {out}")
        return

    env = os.environ.copy()
    for var, default in (("APPTAINER_TMPDIR", "/tmp/apptainer-tmp"), ("APPTAINER_CACHEDIR", "/tmp/apptainer-cache")):
        env.setdefault(var, default)
        Path(env[var]).mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    cmd = [APPTAINER, "build", *shlex.split(args.build_opts), str(out), str(deffile)]
    print("+ " + shlex.join(cmd), file=sys.stderr)
    if subprocess.run(cmd, env=env).returncode != 0:
        die("apptainer build failed (if fakeroot is not set up on this host, rerun with sudo"
            " or pass --build-opts='' as root)")

    print("Verifying patched image ...", file=sys.stderr)
    if not verify_image(out, patches):
        failed = out.with_name(out.name[:-4] + ".FAILED.sif")
        out.rename(failed)
        die(f"verification failed; image moved to {failed} so it cannot be installed by mistake")

    sidecar = out.with_suffix(".patches.json")
    sidecar.write_text(json.dumps(provenance, indent=2) + "\n")
    shutil.rmtree(work)
    print(f"\nBuilt and verified: {out}")
    print(f"Provenance:         {sidecar}")
    print(f"Install with:       make install sif={out} [link-latest=1] [link-stable=1]")


# --------------------------------------------------------------------------- interaction

def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        die("no input available; run without --interactive")


def choose_base(images_dir):
    sifs = sorted(images_dir.glob("*.sif"), key=lambda p: p.stat().st_mtime, reverse=True)
    sifs = [s for s in sifs if not s.name.endswith(".FAILED.sif")]
    if not sifs:
        die(f"no SIF files found in {images_dir}")
    print(f"Base images in {images_dir} (newest first):")
    for i, s in enumerate(sifs, 1):
        print(f"  {i:2d}) {s.name}  ({s.stat().st_size / 2**30:.1f} GiB)")
    choice = ask("Choose a base image by number: ")
    if not choice.isdigit() or not 1 <= int(choice) <= len(sifs):
        die("invalid choice")
    return sifs[int(choice) - 1]


def print_versions(info):
    print("Base versions:")
    for tool, version in sorted(info["versions"].items()):
        print(f"  {tool:12s} {version}  [{info['version_sources'][tool]}]")
    if info["patches"]:
        print("Already patched with: " + ", ".join(p.get("name", "?") for p in info["patches"]))


def parse_assumed(items):
    assumed = {}
    for item in items:
        if "=" not in item:
            die(f"--assume-version expects tool=version, got '{item}'")
        tool, version = item.split("=", 1)
        assumed[tool.strip()] = version.strip()
    return assumed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="path to the base SIF")
    ap.add_argument("--patch", action="append", default=[], help="patch name (repeatable)")
    ap.add_argument("--list", action="store_true", help="show every patch and whether it applies to --base")
    ap.add_argument("--interactive", action="store_true", help="choose base and patches from prompts")
    ap.add_argument("--patches-dir", default=str(DEFAULT_PATCHES_DIR))
    ap.add_argument("--images-dir", default=str(DEFAULT_IMAGES_DIR), help="where --interactive looks for bases")
    ap.add_argument("--out-dir", default=str(REPO / "build"))
    ap.add_argument("--build-opts", default="--fakeroot", help="extra options for apptainer build")
    ap.add_argument("--assume-version", action="append", default=[], metavar="TOOL=VERSION",
                    help="override a base tool version the probes cannot read; recorded in provenance")
    ap.add_argument("--dry-run", action="store_true", help="write the definition file but do not build")
    args = ap.parse_args()

    patches_dir = Path(args.patches_dir)
    if args.interactive and not args.base:
        base = choose_base(Path(args.images_dir))
    elif args.base:
        base = Path(args.base)
    else:
        die("--base is required (or use --interactive)")
    if not base.is_file():
        die(f"base image not found: {base}")
    base = base.resolve()

    if args.list or args.interactive:
        names = list_patch_names(patches_dir)
        if not names:
            die(f"no patches found in {patches_dir}")
    else:
        names = args.patch
        if not names:
            die("give at least one --patch (or use --list / --interactive)")
        if len(set(names)) != len(names):
            die("the same patch was requested twice")

    loaded, load_errors = [], {}
    for name in names:
        try:
            loaded.append(load_patch(patches_dir, name))
        except PatchError as e:
            if args.list or args.interactive:
                load_errors[name] = str(e)
            else:
                die(str(e))

    try:
        info = probe_base(base, {f["replace"] for p in loaded for f in p["files"]})
        assumed = parse_assumed(args.assume_version)
        for tool, version in assumed.items():
            info["versions"][tool] = version
            info["version_sources"][tool] = "assumed (--assume-version)"
        verdicts = {p["name"]: eligibility(p, info) for p in loaded}
    except PatchError as e:
        die(str(e))

    print(f"Base: {base}")
    print_versions(info)

    if args.list or args.interactive:
        print("\nPatches:")
        for p in loaded:
            reasons = verdicts[p["name"]]
            status = "eligible" if not reasons else "not eligible: " + "; ".join(reasons)
            print(f"  {p['name']}  [{status}]")
            if p.get("description"):
                print(f"      {p['description']}")
        for name, err in load_errors.items():
            print(f"  {name}  [broken: {err}]")
        if args.list:
            return
        eligible = [p for p in loaded if not verdicts[p["name"]]]
        if not eligible:
            die("no eligible patches for this base")
        selected = [p for p in eligible if ask(f"Apply {p['name']}? [y/N] ").lower() in ("y", "yes")]
        if not selected:
            print("Nothing selected.")
            return
    else:
        bad = {n: r for n, r in verdicts.items() if r}
        if bad:
            msg = "\n".join(f"  {n}: " + "; ".join(r) for n, r in bad.items())
            die("not every requested patch applies to this base:\n" + msg)
        selected = loaded

    seen = {}
    for p in selected:
        for f in p["files"]:
            if f["replace"] in seen:
                die(f"{p['name']} and {seen[f['replace']]} both replace {f['replace']}")
            seen[f["replace"]] = p["name"]

    print("\nWill build: " + str(Path(args.out_dir).resolve() / output_name(base, selected)))
    print("Applying:   " + ", ".join(p["name"] for p in selected))
    if args.interactive and ask("Proceed? [y/N] ").lower() not in ("y", "yes"):
        print("Cancelled.")
        return
    build(args, base, info, selected, assumed)


if __name__ == "__main__":
    main()
