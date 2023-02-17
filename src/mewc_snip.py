import os
import json
from tqdm import tqdm
from pathlib import Path
from lib_common import read_yaml
from lib_tools import contains_animal
import visualization.visualization_utils as viz_utils

config = read_yaml('config.yaml')
for conf_key in config.keys():
    if conf_key in os.environ:
        config[conf_key] = os.environ[conf_key]

json_path = Path(config['INPUT_DIR'],config['MD_FILE'])
Path(config['INPUT_DIR'],config['SNIP_DIR']).mkdir(parents=True, exist_ok=True)

with open(json_path, "r") as read_json:
    json_data = json.load(read_json)
print("Processing " + str(len(json_data['images'])) + " images from " + config['MD_FILE'])
for json_image in tqdm(json_data['images']):
    try:
        if(contains_animal(json_image)):
            image_name = Path(json_image.get('file')).name
            image_stem = Path(json_image.get('file')).stem
            image_ext = Path(json_image.get('file')).suffix
            input_path = Path(config['INPUT_DIR'],image_name)
            if(input_path.is_file()):
                pil_image = viz_utils.load_image(input_path)
                crops = viz_utils.crop_image(detections=json_image['detections'],image=pil_image,confidence_threshold=float(config['LOWER_CONF']))
                crop_num = 0;
                for crop in crops:
                    if(json_image['detections'][crop_num].get('category')=='1'): #check if we are snipping an animal
                        resized_crop = viz_utils.resize_image(crop,int(config['SNIP_SIZE']),int(config['SNIP_SIZE']))
                        output_path = Path(config['INPUT_DIR'],config['SNIP_DIR'],image_stem+'-'+str(crop_num)+image_ext)
                        resized_crop.save(output_path)
                        crop_num += 1
    except: pass
