# mewc-snip

## Introduction
This repository contains code to build a Docker container for running mewc-snip. This is a tool used to snip detections from camera trap images identified in  [MegaDetector](https://github.com/microsoft/CameraTraps/blob/main/megadetector.md) JSON output. 

You can supply arguments via an environment file where the contents of that file are in the following format with one entry per line:
```
VARIABLE=VALUE
```

## Usage

After installing Docker you can run the container using a command similar to the following. Substitute `"$IN_DIR"` for your image directory and create a text file `"$ENV_FILE"` with any config options you wish to override. 

```
docker pull zaandahl/mewc-snip:v1.0
docker run --env-file "$ENV_FILE" \
    --interactive --tty --rm \
    --volume "$IN_DIR":/images \
    zaandahl/mewc-snip
```

## Config Options

The following environment variables are supported for configuration (and their default values are shown). Simply omit any variables you don't need to change and if you want to just use all defaults you can leave `--env-file megadetector.env` out of the command alltogether. 

| Variable | Default | Description |
| ---------|---------|------------ |
| INPUT_DIR | "/images/" | A mounted point containing images to process - must match the Docker command above |
| MD_FILE | "md_out.json" | MegaDetector output file, must be located in INPUT_DIR |
| SNIP_DIR | "snips" | A subdirectory under INPUT_DIR to save snips (will be created if it does not exist) |
| LOWER_CONF | 0.05 | The lowest detection confidence threshold to accept for snipping |
| SNIP_SIZE | 600 | The pixel size for the saved snips (square) |
