"""Crop eligible animals without changing source files or losing detection identity."""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import yaml
from lib_command import integer, relative_path
from lib_tools import validate_detections, process_detections, DEFAULT_POLICY

CROP_POLICY = DEFAULT_POLICY
FILTER_DEFAULTS = dict(OVERLAP=.3, EDGE_DIST=.02, MIN_EDGES=0, UPPER_CONF=.9)


def atomic_json(path, document):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.manifest-', suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(document, stream, indent=2, allow_nan=False)
            stream.write('\n')
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run(config, visualization=None):
    root = Path(config['INPUT_DIR']).resolve()
    if not root.is_dir():
        raise ValueError('INPUT_DIR must exist')
    output_dir = relative_path(root, config['SNIP_DIR'], 'SNIP_DIR')
    json_path = relative_path(root, config['MD_FILE'], 'MD_FILE')
    if output_dir == json_path or output_dir in json_path.parents:
        raise ValueError('SNIP_DIR cannot contain the detector input JSON')
    threshold = float(config['LOWER_CONF'])
    size = integer(config['SNIP_SIZE'], 'SNIP_SIZE')
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('LOWER_CONF must be finite and between 0 and 1')
    output_dir.mkdir(parents=True, exist_ok=True)
    # Fail closed before reading detector input or loading an optional runtime dependency.
    manifest_path = output_dir / 'crop_manifest.json'
    policy = config.get('SUPPRESSION_POLICY', CROP_POLICY)
    manifest = {'schema_version': 1, 'policy': policy, 'selection': 'animal', 'complete': False,
                'effective_options': {'LOWER_CONF': threshold, 'SNIP_SIZE': size},
                'crops': [], 'omissions': [], 'errors': [], 'images': []}
    atomic_json(manifest_path, manifest)
    try:
        filtering = {key: config.get(key, default) for key, default in FILTER_DEFAULTS.items()}
        filtering['MIN_EDGES'] = integer(filtering['MIN_EDGES'], 'MIN_EDGES', minimum=0)
        for key in ('OVERLAP', 'EDGE_DIST', 'UPPER_CONF'):
            filtering[key] = float(filtering[key])
            if not math.isfinite(filtering[key]) or not 0 <= filtering[key] <= 1:
                raise ValueError(f'{key} must be finite and between 0 and 1')
        manifest['effective_options'].update(filtering)
        with open(json_path, encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or not isinstance(data.get('images'), list):
            raise ValueError('Detector JSON must contain an images list')
        if visualization is None:
            from megadetector.visualization import visualization_utils as visualization
        seen_sources = set()
        for json_image in data['images']:
            source_file = json_image.get('file') if isinstance(json_image, dict) else None
            image_record = {'source_file': source_file, 'status': 'failed', 'eligible': 0, 'written': 0}
            manifest['images'].append(image_record)
            try:
                source = relative_path(root, source_file, 'image file')
                source_file = source.relative_to(root).as_posix()
                image_record['source_file'] = source_file
                if source_file in seen_sources:
                    raise ValueError('Duplicate source image in detector JSON')
                seen_sources.add(source_file)
                if output_dir == source or output_dir in source.parents:
                    raise ValueError('Source images cannot be inside SNIP_DIR')
                detections = validate_detections(json_image)
                mask = process_detections(json_image, filtering['OVERLAP'], filtering['EDGE_DIST'],
                                          filtering['MIN_EDGES'], filtering['UPPER_CONF'], threshold,
                                          policy=policy)
                selected = []
                for index, detection in enumerate(detections):
                    if detection['category'] != '1':
                        reason = 'non-animal'
                    elif detection['conf'] < threshold:
                        reason = 'below-confidence-threshold'
                    elif not mask[index]:
                        reason = 'suppressed-by-' + policy
                    else:
                        selected.append((index, detection))
                        continue
                    manifest['omissions'].append({'source_file': source_file,
                                                   'detection_index': index, 'reason': reason})
                image_record['eligible'] = len(selected)
                # Check every listed source, including valid zero-detection images.
                if not source.is_file():
                    raise FileNotFoundError(f'Source image does not exist: {source_file}')
                pil_image = visualization.load_image(str(source))
                if selected:
                    try:
                        for index, detection in selected:
                            crop_rel = Path(source_file).with_name(f'{source.stem}-{index}{source.suffix}')
                            output = relative_path(output_dir, crop_rel.as_posix(), 'crop file')
                            output.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                # Never infer identity from a threshold-filtered list position.
                                crops = visualization.crop_image([detection], pil_image,
                                                                  confidence_threshold=threshold)
                                if len(crops) != 1 or min(crops[0].size) <= 0:
                                    raise ValueError('Eligible detection did not yield one nonempty crop')
                                resized = visualization.resize_image(crops[0], size, size)
                                with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.crop-',
                                                                 suffix=output.suffix, delete=False) as stream:
                                    temporary = Path(stream.name)
                                try:
                                    resized.save(temporary)
                                    temporary.replace(output)
                                finally:
                                    temporary.unlink(missing_ok=True)
                                manifest['crops'].append({'crop_id': crop_rel.as_posix(),
                                                          'crop_file': crop_rel.as_posix(),
                                                          'source_file': source_file, 'detection_index': index})
                                image_record['written'] += 1
                            except Exception as exc:
                                manifest['errors'].append({'source_file': source_file,
                                                           'detection_index': index, 'reason': str(exc)})
                    finally:
                        pil_image.close()
                else:
                    pil_image.close()
                image_record['status'] = ('complete' if image_record['written'] == image_record['eligible']
                                          else 'failed')
            except Exception as exc:
                manifest['errors'].append({'source_file': source_file, 'reason': str(exc)})
        expected = {crop['crop_file'] for crop in manifest['crops']}
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.gif'}
        stale = sorted(path.relative_to(output_dir).as_posix() for path in output_dir.rglob('*')
                       if path.is_file() and path.suffix.lower() in image_extensions
                       and path.relative_to(output_dir).as_posix() not in expected)
        if stale:
            manifest['errors'].append({'reason': 'Unlisted crop files; use a fresh SNIP_DIR', 'files': stale})
        manifest['counts'] = {'images': len(data['images']),
                              'images_complete': sum(row['status'] == 'complete' for row in manifest['images']),
                              'eligible': sum(row['eligible'] for row in manifest['images']),
                              'written': len(manifest['crops']), 'omitted': len(manifest['omissions']),
                              'errors': len(manifest['errors'])}
        manifest['complete'] = (not manifest['errors'] and
                                manifest['counts']['eligible'] == manifest['counts']['written'])
    except Exception as exc:
        manifest['errors'].append({'reason': str(exc)})
    atomic_json(manifest_path, manifest)
    print(json.dumps({'complete': manifest['complete'], 'counts': manifest.get('counts'),
                      'errors': manifest['errors']}), flush=True)
    return manifest


def main(config_path=None):
    try:
        with open(config_path or Path(__file__).with_name('config.yaml'), encoding='utf-8') as stream:
            config = yaml.safe_load(stream)
        if not isinstance(config, dict):
            raise ValueError('Configuration must be a mapping')
        config = {**FILTER_DEFAULTS, **config}
        config.update({key: os.environ[key] for key in config if key in os.environ})
        return 0 if run(config)['complete'] else 1
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        print(f'Snipping failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
