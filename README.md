<img src="mewc_logo_hex.png" alt="MEWC Hex Sticker" width="200" align="right"/>

# mewc-snip

The integrity changes in this checkout require the source builds described in [BUILDING.md](BUILDING.md). Published legacy tags do not provide these fixes. Use the tested image ID or digest from the generated image lock.

## Introduction
This repository contains code to build a Docker container for running mewc-snip. This is a tool used to snip detections from camera trap images identified in  [MegaDetector](https://github.com/microsoft/CameraTraps/blob/main/megadetector.md) JSON output. 

You can supply arguments via an environment file where the contents of that file are in the following format with one entry per line:
```
VARIABLE=VALUE
```

## Usage

After installing Docker you can run the container using a command similar to the following. Substitute `"$IN_DIR"` for your image directory and create a text file `"$ENV_FILE"` with any config options you wish to override. 

```
# Set STAGE_IMAGE to this stage's immutable image ID or registry digest from the generated image lock.
: "${STAGE_IMAGE:?Set the reviewed stage image}"
docker run --env-file "$ENV_FILE" \
    --interactive --tty --rm \
    --volume "$IN_DIR":/images \
    "$STAGE_IMAGE"
```

## Config Options

The following environment variables are supported for configuration (and their default values are shown). Simply omit any variables you don't need to change and if you want to just use all defaults you can leave `--env-file $ENV_FILE` out of the command alltogether. 

| Variable | Default | Description |
| ---------|---------|------------ |
| INPUT_DIR | "/images/" | A mounted point containing images to process - must match the Docker command above |
| MD_FILE | "md_out.json" | MegaDetector output file, must be located in INPUT_DIR |
| SNIP_DIR | "snips" | A subdirectory under INPUT_DIR to save snips (will be created if it does not exist) |
| LOWER_CONF | 0.05 | The lowest detection confidence threshold to accept for snipping |
| SNIP_SIZE | 600 | The pixel size for the saved snips (square) |

## Crop identity and completion

Each animal accepted by the explicitly selected shared suppression policy is
cropped from its original MegaDetector detection index (zero-based). Cropping
uses MegaDetector's image loading, bounding-box crop and square resizing helpers;
original images are only read. A preceding person or rejected low-confidence
entry cannot shift the animal's index. The current package import is
`megadetector.visualization.visualization_utils`.

Relative paths are retained. For example, detection 2 from `station-a/IMG001.JPG`
becomes `snips/station-a/IMG001-2.JPG`. `crop_manifest.json` inside `SNIP_DIR` is the
authoritative join to downstream prediction and metadata:

```json
{
  "schema_version": 1,
  "policy": "category-confidence-v1",
  "selection": "animal",
  "complete": true,
  "crops": [{
    "crop_id": "station-a/IMG001-2.JPG",
    "crop_file": "station-a/IMG001-2.JPG",
    "source_file": "station-a/IMG001.JPG",
    "detection_index": 2
  }]
}
```

The full manifest also records effective options, each image's completion status,
counts, detection exclusions with reasons, and errors. It is marked incomplete
before processing and atomically replaced after accounting. Crop files are written
atomically. Any unreadable/missing source, malformed detection, failed crop, duplicate
source identity or leftover unlisted crop yields a nonzero stage exit. A valid
empty detection list has successful zero-crop accounting. Downstream stages must
require `complete=true` and use manifest identities, never reconstruct identity
from a filtered-list position or a basename match.

Use a fresh `SNIP_DIR` when changing inputs or policy. Unlisted old crops are
reported without deleting them. Absolute/traversing paths and symlink escapes are
rejected, and sources cannot be within the crop output directory.

The default `SUPPRESSION_POLICY=category-confidence-v1` uses the same accepted
mask as boxing and metadata, then selects animal category `1`. In addition to
`LOWER_CONF`, its inherited settings are `OVERLAP=0.3`, `EDGE_DIST=0.02`,
`MIN_EDGES=0`, and `UPPER_CONF=0.9`. Confidence filtering precedes same-category
suppression in descending confidence order. These numeric defaults are unchanged.
The policy was changed explicitly for new runs; it can alter crop counts compared
with older confidence-only snipping. The optional `legacy-matryoshka-v1` helper
policy reproduces historical box/metadata suppression, not historical confidence-only
snip selection. Do not compare counts from different policies as if they were equal.

Lightweight regression checks use pytest, PyYAML and Pillow, with a small Pillow
backend substituting only for MegaDetector's visualization dependency:

```sh
# Keep the mewc-detect checkout adjacent, or put its src directory on PYTHONPATH.
python -m pytest -q tests
```

The fixtures cover person-first and filtered detections, original indices, nested
duplicate basenames, multiple eligible animals, immutable source bytes, malformed
and missing inputs, partial crop failures, stale crops and suppression accounting.
They do not run MegaDetector inference or certify the container's dependency stack.
