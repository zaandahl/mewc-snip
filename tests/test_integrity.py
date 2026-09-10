import hashlib
import json
from pathlib import Path
import sys
import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'src'), str(REPO.parent / 'mewc-detect' / 'src')]
from mewc_snip import run, main


class PillowVisualization:
    """Small real-image backend; tests stage behavior without loading ML frameworks."""
    @staticmethod
    def load_image(path):
        image = Image.open(path)
        image.load()
        return image

    @staticmethod
    def crop_image(detections, image, confidence_threshold):
        assert len(detections) == 1
        assert detections[0]['conf'] >= confidence_threshold
        x, y, w, h = detections[0]['bbox']
        return [image.crop((x*image.width, y*image.height, (x+w)*image.width, (y+h)*image.height))]

    @staticmethod
    def resize_image(image, width, height):
        return image.resize((width, height), Image.Resampling.LANCZOS)


def detection(category='1', confidence=.7, bbox=None):
    return {'category': category, 'conf': confidence, 'bbox': bbox or [.1, .1, .4, .4]}


def prepare(tmp_path, records):
    (tmp_path / 'md_out.json').write_text(json.dumps({'images': records}))
    return dict(INPUT_DIR=str(tmp_path), MD_FILE='md_out.json', SNIP_DIR='snips', LOWER_CONF=.05,
                SNIP_SIZE=20, OVERLAP=.3, EDGE_DIST=.02, MIN_EDGES=0, UPPER_CONF=.9,
                SUPPRESSION_POLICY='category-confidence-v1')


def create_image(tmp_path, name, color='red'):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (40, 30), color).save(path)
    return path


def test_person_first_filtered_indices_nested_duplicates_and_immutable_sources(tmp_path):
    records = []
    hashes = {}
    for directory, color in [('one', 'red'), ('two', 'blue')]:
        name = f'{directory}/same.png'
        path = create_image(tmp_path, name, color)
        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({'file': name, 'detections': [detection('2'), detection(confidence=.01), detection()]})
    manifest = run(prepare(tmp_path, records), PillowVisualization)
    assert manifest['complete']
    assert [crop['crop_file'] for crop in manifest['crops']] == ['one/same-2.png', 'two/same-2.png']
    assert [crop['detection_index'] for crop in manifest['crops']] == [2, 2]
    assert manifest['counts'] == dict(images=2, images_complete=2, eligible=2, written=2, omitted=4, errors=0)
    assert {row['reason'] for row in manifest['omissions']} == {'non-animal', 'below-confidence-threshold'}
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == value for path, value in hashes.items())
    assert Image.open(tmp_path / 'snips/one/same-2.png').getpixel((10, 10)) == (255, 0, 0)
    assert Image.open(tmp_path / 'snips/two/same-2.png').getpixel((10, 10)) == (0, 0, 255)


def test_each_eligible_animal_is_cropped_by_original_index(tmp_path):
    create_image(tmp_path, 'source.png')
    record = {'file': 'source.png', 'detections': [detection('2'), detection(bbox=[0, 0, .3, .3]),
                                                detection(bbox=[.6, .6, .3, .3])]}
    manifest = run(prepare(tmp_path, [record]), PillowVisualization)
    assert manifest['complete']
    assert [row['detection_index'] for row in manifest['crops']] == [1, 2]


@pytest.mark.parametrize('record', [
    {'file': 'missing.png', 'detections': [detection()]},
    {'file': 'source.png', 'failure': 'decode', 'detections': None},
    {'file': '../outside.png', 'detections': [detection()]},
    {'file': 'source.png', 'detections': [dict(detection(), bbox=None)]},
])
def test_errors_persist_in_incomplete_manifest(tmp_path, record):
    create_image(tmp_path, 'source.png')
    manifest = run(prepare(tmp_path, [record]), PillowVisualization)
    assert not manifest['complete']
    assert manifest['errors']
    assert json.loads((tmp_path / 'snips/crop_manifest.json').read_text()) == manifest


def test_valid_zero_has_complete_accounting(tmp_path):
    create_image(tmp_path, 'source.png')
    manifest = run(prepare(tmp_path, [{'file': 'source.png', 'detections': []}]), PillowVisualization)
    assert manifest['complete'] and manifest['counts']['written'] == 0
    assert manifest['images'][0]['status'] == 'complete'


def test_crop_failure_is_explicit(tmp_path):
    class Broken(PillowVisualization):
        @staticmethod
        def crop_image(*args, **kwargs):
            raise OSError('injected crop failure')
    create_image(tmp_path, 'source.png')
    manifest = run(prepare(tmp_path, [{'file': 'source.png', 'detections': [detection()]}]), Broken)
    assert not manifest['complete']
    assert manifest['counts']['eligible'] == 1 and manifest['counts']['written'] == 0
    assert manifest['errors'][0]['detection_index'] == 0


def test_stale_crops_fail_without_deleting_them(tmp_path):
    create_image(tmp_path, 'source.png')
    stale = create_image(tmp_path, 'snips/stale.png')
    manifest = run(prepare(tmp_path, [{'file': 'source.png', 'detections': []}]), PillowVisualization)
    assert not manifest['complete']
    assert stale.exists()
    assert 'fresh SNIP_DIR' in manifest['errors'][0]['reason']


def test_manifest_invalidated_before_invalid_json(tmp_path):
    cfg = prepare(tmp_path, [])
    run(cfg, PillowVisualization)
    (tmp_path / 'md_out.json').write_text('{invalid')
    manifest = run(cfg, PillowVisualization)
    assert not manifest['complete'] and manifest['errors']


def test_shared_suppression_applies_to_crops(tmp_path):
    create_image(tmp_path, 'source.png')
    manifest = run(prepare(tmp_path, [{'file': 'source.png', 'detections': [detection(), detection(confidence=.5)]}]), PillowVisualization)
    assert manifest['complete']
    assert [row['detection_index'] for row in manifest['crops']] == [0]
    assert manifest['omissions'][0]['reason'] == 'suppressed-by-category-confidence-v1'


def test_corrupt_blank_source_is_not_complete(tmp_path):
    (tmp_path / 'broken.png').write_bytes(b'not an image')
    manifest = run(prepare(tmp_path, [{'file': 'broken.png', 'detections': []}]), PillowVisualization)
    assert not manifest['complete']
    assert manifest['images'][0]['status'] == 'failed'
    assert manifest['errors']


@pytest.mark.parametrize('present, expected_exit', [(True, 0), (False, 1)])
def test_snip_entrypoint_reports_success_and_failure(tmp_path, present, expected_exit):
    import os
    import subprocess
    if present:
        create_image(tmp_path, 'source.png')
    config = prepare(tmp_path, [{'file': 'source.png', 'detections': []}])
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(json.dumps(config))
    package = tmp_path / 'megadetector' / 'visualization'
    package.mkdir(parents=True)
    (package / 'visualization_utils.py').write_text(
        'from PIL import Image\ndef load_image(path):\n    image = Image.open(path)\n    image.load()\n    return image\n')
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(tmp_path), str(REPO / 'src'),
                                                      str(REPO.parent / 'mewc-detect' / 'src')])}
    result = subprocess.run([sys.executable, '-c',
                             'import sys; from mewc_snip import main; sys.exit(main(sys.argv[1]))',
                             str(config_path)], env=env, capture_output=True, text=True)
    assert result.returncode == expected_exit, result.stderr
    manifest = json.loads((tmp_path / 'snips/crop_manifest.json').read_text())
    assert manifest['complete'] is present
