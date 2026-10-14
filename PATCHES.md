# Patched images

A patched image is an existing base SIF with specific files replaced, used to fix a tool inside
the container without rebuilding it. The base is never rebuilt: the patched SIF bootstraps from
the exact base file, so it is the base plus the listed replacements and nothing else. This matters
because base builds are not reproducible (unpinned `apt-get update`, AFNI installed from `master`,
`conda update`), so rebuilding a base to add a patch would quietly change everything else too.

## Requirements

- Apptainer 1.1 or later and Python 3.8 or later.
- A base SIF to patch, built with `make sif` or taken from an existing install.
- Free local disk for Apptainer's temp directory (`/tmp/apptainer-tmp` by default) of roughly
  three times the base SIF's size, since the base is unpacked during the build, plus the base
  SIF's size again for the output in `build/`.
- A build host that allows unprivileged user namespaces: `unshare -Ur true` succeeds. If it
  doesn't, see [Building as root](#building-as-root).

## Building a patched image

```bash
# first put each patch payload in place: see "Patch payloads" below

make patch-list base=/path/to/base.sif       # which patches apply to this base, and why not
make patch base=/path/to/base.sif patches="atropos251 qatoolsfix"
```

The result is `build/<base>+atropos251-qatoolsfix.sif`, with its provenance record in
`build/<base>+atropos251-qatoolsfix.patches.json`. Each patch's test has already run inside the
image by the time the build reports success. If `/tmp` lacks space, add
`APPTAINER_TMPDIR=/other/local/dir` to the `make patch` command; local disk works more reliably
than NFS here.

To patch an image that is already patched, pass it as `base=` and list only the new patches. The
result is named `<base>+atropos251-qatoolsfix+<new>.sif` and its record keeps the full history.

`make patch-interactive` picks the base and patches from prompts instead.

## Installing and publishing

```bash
# Install and point "latest" at it for testing; "stable" is untouched
make install sif=build/<base>+<patches>.sif prefix=/path/to/containers project=ncanda link-latest=1

# After testing, point "stable" at it
make install sif=build/<base>+<patches>.sif prefix=/path/to/containers project=ncanda link-stable=1
```

`install` copies the image and its `.patches.json` to `<prefix>/images/`. With `link-latest=1` or
`link-stable=1` it points `<prefix>/<project>-image-processing-latest.sif` or `-stable.sif` at
the image; without either flag no link changes. `prefix` defaults to `install/` in this repository. `project` (`ncanda` or
`hivalc`) defaults to `sibis`, which no launcher uses, so always set it when moving links.

To roll back, point the link at the previous image again:
`ln -sfn <prefix>/images/<previous>.sif <prefix>/<project>-image-processing-stable.sif`.

## Checking what an image contains

```bash
apptainer inspect --labels <image.sif> | grep org.sibis
apptainer exec <image.sif> cat /opt/sibis-patches/PATCHES.json
```

Unpatched images have no `org.sibis` labels. The same record is also next to each installed image
as `<image>.patches.json`.

## Building as root

If unprivileged user namespaces are blocked on the build host, build as root onto local disk,
then install as yourself. Writing to NFS as root often fails because of root squashing.

```bash
sudo git config --global --add safe.directory "$PWD"     # lets root read this repo's commit for the record
sudo make patch base=/path/to/base.sif patches="atropos251 qatoolsfix" patch-build-opts= BUILD_DIR=/var/tmp/patchbuild
make install sif=/var/tmp/patchbuild/<base>+<patches>.sif prefix=/path/to/containers project=ncanda link-latest=1
sudo rm -rf /var/tmp/patchbuild /tmp/apptainer-tmp /tmp/apptainer-cache
```

The record will show `built_by: root`.

## What a patch build does

1. **Checks the patch files.** Each file's sha256 must match its manifest. An un-pulled Git LFS
   pointer fails here with a hint to run `git lfs pull`.
2. **Inspects the base.** Reads tool versions (from `/usr/local/tools/VERSIONS.json` if the base
   has one, otherwise from the probes in `bin/patch-sif.py`), any earlier patches, and the sha256
   of every file to be replaced.
3. **Checks eligibility.** Refuses the build if any requested patch:
   - has a version requirement the base doesn't meet,
   - targets a file the base doesn't have,
   - was already applied, or
   - targets a file whose sha256 differs from `replaces_sha256`, when the manifest sets one.
4. **Builds.** Generates an Apptainer definition file (`Bootstrap: localimage`, `From:` the base)
   that keeps each original as `<file>.orig`, puts the new file in place with the original's mode
   and owner, and checks its sha256.
5. **Verifies.** Rechecks every replaced file in the finished image and runs each patch's
   `verify.sh` inside it. A failed image is renamed `*.FAILED.sif` so `make install` cannot pick
   it up.
6. **Records provenance**, in three places:
   - `/opt/sibis-patches/PATCHES.json` inside the image,
   - `<output>.patches.json` next to the SIF (copied by `make install`),
   - `org.sibis.*` labels (`apptainer inspect --labels <sif>`).

   It covers the base SIF's name and sha256, base tool versions and where each came from, and for
   every patch: its origin, the original and new sha256 of each file, and the
   commit of this repo.

## Adding a patch

Create `patches/<name>/` containing the replacement file(s), a `manifest.json`, and optionally a
`verify.sh`. The name is short, lowercase letters and digits only, and becomes part of image
filenames.

```json
{
  "name": "<name, same as the directory>",
  "tag": "<same as name>",
  "description": "<one line: what it changes and why>",
  "requires": { "<tool>": "<spec, e.g. >=2.5.2 or ==7.3.2 or >=7.3,<7.5>" },
  "files": [
    {
      "src": "<file in this directory>",
      "replace": "<absolute path inside the image>",
      "sha256": "<sha256 of src>",
      "replaces_sha256": "<optional: sha256 the original must have>"
    }
  ],
  "origin": "<where the replacement came from, precisely enough to re-obtain and re-verify it>",
  "verify": "verify.sh"
}
```

To find the file to replace and its current hash in a base:
`apptainer exec <base.sif> bash -c 'find /usr/local/tools -name <filename>'` and
`apptainer exec <base.sif> sha256sum <path>`.

Guidelines:

- Use `==` when the replacement is a modified copy of one specific version's file. Applying it to
  another version would silently revert that version's other changes. Set `replaces_sha256` in
  that case too.
- `verify.sh` runs inside the patched image. Make it a regression test where possible: something
  that fails on the original and passes on the patch.
- Version requirements work for `ants` and `freesurfer`. Another tool needs an entry in `PROBES`
  in `bin/patch-sif.py`; for a one-off, `--assume-version tool=X.Y.Z` works and is recorded in
  provenance as assumed.
- Binaries go through Git LFS. Add a line to `.gitattributes` before the first `git add`, e.g.
  `patches/<name>/<binary> filter=lfs diff=lfs merge=lfs -text`, then confirm with
  `git lfs ls-files`.
- Check the patch applies with `make patch-list base=<base.sif>` before opening a pull request.

## Current patches

**`atropos251`** (requires ANTs 2.5.2 or later). Replaces `Atropos` with the unmodified binary
from the official ANTs v2.5.1 release (`ants-2.5.1-ubuntu-22.04-X64-gcc.zip`,
`ants-2.5.1/bin/Atropos`, sha256 `f67ea83c…dc998e70d`); the rest of ANTs stays at the base's
version. From 2.5.2, Atropos fails when partial-volume likelihoods leave requested tissue classes
empty. ITK is compiled into the binary, which needs only glibc 2.34+ and GCC 11+ libstdc++, so it
runs on the Ubuntu 24.04 base. Needed by sibis-platform/ncanda-image-processing-scripts#4
(Minhui Yu), which restored partial-volume Atropos segmentation.

**`qatoolsfix`** (requires FreeSurfer 7.3.2 exactly). Replaces `qatoolspython/checkTopology.py`
with FreeSurfer 7.3.2's own copy plus one fix backported from upstream fsqc: the six return values
are initialized to NaN before `recon-all.log` is parsed. The stock 7.3.2 function raises
`UnboundLocalError` when any expected log line is missing; the patched one returns NaN for that
value. This is not the latest fsqc, which computes hole counts from the surfaces with `lapy` and
could give different numbers. `verify.sh` runs the function on an empty log and requires NaNs,
which fails on the stock file. Needed by sibis-platform/ncanda-image-processing-scripts#2
(Minhui Yu).
## Patch payloads

The replacement files come from the tools' own releases and are not included here. Put each one in
place before building a patched image:

- **atropos251:** `patches/atropos251/Atropos` is `ants-2.5.1/bin/Atropos` from the official ANTs
  v2.5.1 release (see `origin` in `patches/atropos251/manifest.json`):

```bash
  curl -LO https://github.com/ANTsX/ANTs/releases/download/v2.5.1/ants-2.5.1-ubuntu-22.04-X64-gcc.zip
  unzip -j ants-2.5.1-ubuntu-22.04-X64-gcc.zip ants-2.5.1/bin/Atropos -d patches/atropos251/
```

- **qatoolsfix:** `patches/qatoolsfix/checkTopology.py` is FreeSurfer 7.3.2's
  `python/packages/qatoolspython/checkTopology.py` with the six return values initialized to NaN
  before `recon-all.log` is parsed, backported from fsqc. Copy the file from your FreeSurfer 7.3.2
  install and make that change.

Each manifest lists the `sha256` of the file NCANDA uses.
