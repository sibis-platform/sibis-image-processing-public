# SIBIS image processing container

Build recipe for the container that runs the NCANDA image processing pipelines
([ncanda-image-processing-scripts-public](https://github.com/sibis-platform/ncanda-image-processing-scripts-public)).
It installs the neuroimaging tools at the paths the pipelines expect, under `/usr/local/tools`.

This repository contains only the recipe and our own build scripts. No third-party software is
included: download each tool from its source, under its own license, at the version listed below
or one you choose.

## Requirements

- Docker with BuildKit to build the image, on a machine with roughly 150 GB of free disk.
- Apptainer 1.1 or later, to convert the image to a SIF file and run it.
- Python 3.8 or later, for building [patched images](PATCHES.md).

## Tool versions

The NCANDA image was built with these versions. Place each download at the path shown under
`resources/`. `resources/MANIFEST.sha256` lists the checksums of the files we used, so you can
confirm you have the same ones: `cd resources && sha256sum -c MANIFEST.sha256`.

| Tool | Version | Place at `resources/...` | Source |
|---|---|---|---|
| FreeSurfer | 7.3.2 (Ubuntu 22 build) | `freesurfer/freesurfer-linux-ubuntu22_amd64-7.3.2.tar.gz` | FreeSurfer (MGH) |
| FreeSurfer license | your own | `freesurfer/license.txt` | free registration on the FreeSurfer website |
| FSL | 6.0.7.4 | `fsl/fslinstaller.py` (the installer downloads FSL during the build) | FSL (FMRIB, Oxford) |
| Connectome Workbench | 1.5.0 | `connectome/workbench-linux64-v1.5.0.zip` | Human Connectome Project |
| Convert3D | 1.3.0 | `c3d/c3d-1.3.0-Linux-gcc64.tar.gz` | c3d on SourceForge |
| CMTK | 3.4.0, source | `cmtk/CMTK-3.4.0-Source.tar.gz` | CMTK on NITRC |
| Camino | commit `1c4ef77615d103d43adcff6c79b72d0bbdac0897` | `camino/camino-code-1c4ef77615d103d43adcff6c79b72d0bbdac0897.zip` | Camino on SourceForge |
| ROBEX | 1.2 | `robex/ROBEXv12.linux64.tar.gz` | ROBEX on NITRC |
| naonlm3d | commit `cf4d499f52c517101b9a6b97bbbb8b4b3e0f250d` | `naonlm3d/naonlm3d-src/` (repository contents) | github.com/djkwon/naonlm3d |
| LWDP | SVN revision 23 | `lwdp/r23/` | `svn export -r 23 https://www.nitrc.org/svn/lwdp/trunk/ resources/lwdp/r23` |
| Miniconda | py39_4.12.0 | `miniconda/Miniconda3-py39_4.12.0-Linux-x86_64.sh` | repo.anaconda.com/miniconda |
| 3D Slicer | 4.4, revision 24545 | `slicer/slicer.tar.gz` (see below) | Slicer |

Installed during the build, so there is nothing to place:

- **ANTs 2.6.3**, cloned from github.com/ANTsX/ANTs and built from source by `resources/ants/setup.sh`.
- **AFNI**, installed with AFNI's Ubuntu 24 install notes. This is not pinned and installs the
  current release; the NCANDA image has AFNI_26.1.00.
- **MATLAB Runtime R2019b** for FreeSurfer, installed with FreeSurfer's `fs_install_mcr`.
- **Ubuntu 24.04 packages** and the **conda environment** in `resources/miniconda/ncanda-3.0.0-environment.yml`.

**Slicer.** The pipelines use Slicer's command-line modules at
`/usr/local/tools/slicer/r24545/Ubuntu14/lib/Slicer-4.4/cli-modules`. Package a Slicer 4.4 Linux
build so that `slicer.tar.gz` extracts to `r24545/Ubuntu14/`.

**Other versions.** The Dockerfile reads archive names and versions from build arguments (for
example `FREESURFER_ARCHIVE`, `CMTK_ARCHIVE`, `CONNECTOME_VERSION`), so you can choose different
versions with `--build-arg`. The pipelines were developed and tested with the versions above.

## Building

```bash
make
```

This builds the Docker image and converts it to `build/sibis-image-processing-latest_<date>_<id>.sif`.

Then apply the patches the pipeline scripts need (see [PATCHES.md](PATCHES.md)). The structural
pipelines need `atropos251` on this build, because it compiles ANTs 2.6.3:

```bash
make patch base=build/<image>.sif patches="atropos251 qatoolsfix"
```

Builds are not fully reproducible: Ubuntu packages, AFNI and conda packages install at their
current versions when you build. Your FreeSurfer license is copied into the image, so do not share
an image you have built.

## Using the image with the pipelines

Generate the pipeline scripts inside the container, with the scripts repository mounted where the
image expects it (`/usr/local/tools/image_processing/bin` is on the image's `PATH`):

```bash
apptainer exec --compat --home /home/ncanda \
  --bind /path/to/ncanda-image-processing-scripts-public:/usr/local/tools/image_processing \
  build/<image>.sif bash -c 'cd /usr/local/tools/image_processing && cmake --preset docker .'
```

Then run a pipeline from your cases directory, with scratch space for intermediate files bound
over `/tmp`:

```bash
apptainer exec --compat --home /home/ncanda \
  --bind /path/to/ncanda-image-processing-scripts-public:/usr/local/tools/image_processing \
  --bind /path/to/cases:/data/cases --bind /path/to/scratch:/tmp --pwd /data/cases \
  build/<image>.sif ncanda_all_pipelines NCANDA_S#####/standard/baseline
```

`--compat` gives the container a clean environment, so pass any variables it needs with `--env`.

## Patches

A patched image is an existing image with specific files replaced, to fix one tool without
rebuilding everything. See [PATCHES.md](PATCHES.md).

## License

The Dockerfile and build scripts in this repository are BSD 3-Clause, Copyright SRI International
and Stanford University. See [`COPYING`](COPYING). Each tool you download is under its own license.

## Support

Please report problems through GitHub issues. The container is maintained by the NCANDA data core
at the Computational Neuroscience Laboratory, Stanford University, on a best-effort basis.
