import contextlib

import gradio as gr
from modules import scripts
from modules import script_callbacks
import json
import os


def get_json_content(file_path):
    try:
        with open(file_path, 'r') as file:
            json_data = json.load(file)
            return json_data
    except Exception as e:
        print(f"A Problem occurred: {str(e)}")


def read_sdxl_styles(json_data):
    # Check that data is a list
    if not isinstance(json_data, list):
        print("Error: input data must be a list")
        return None

    names = []

    # Iterate over each item in the data list
    for item in json_data:
        # Check that the item is a dictionary
        if isinstance(item, dict):
            # Check that 'name' is a key in the dictionary
            if 'name' in item:
                # Append the value of 'name' to the names list
                names.append(item['name'])

    return names


def send_text_to_prompt(new_text, old_text):
    if old_text == "":  # if text on the textbox text2img or img2img is empty, return new text
        return new_text
    # else join them together and send it to the textbox
    return old_text + " " + new_text


def getStyles():
    json_path = os.path.join(scripts.basedir(), 'sdxl_styles.json')
    json_data = get_json_content(json_path)
    styles = read_sdxl_styles(json_data)
    return styles


class StyleSelectorXL(scripts.Script):
    def __init__(self) -> None:
        super().__init__()

    styleNames = getStyles()

    def title(self):
        return "Style Selector for SDXL 1.0"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Group():
            with gr.Accordion("Select Style", open=False):
                is_enabled = gr.Checkbox(
                    value=True, label="Enable Style Selector")
                style = gr.Radio(self.styleNames, label="Location",
                                 info="Where did they go?"),
                text_to_be_sent = gr.Textbox(label="drop text")

        # Ignore the error if the attribute is not present

        return [is_enabled, text_to_be_sent,style]

    def process(self, p, is_enabled, text_to_be_sent,style):
        if not is_enabled:
            return

        p.extra_generation_params["Style Selector Enabled"] = True

        for i, prompt in enumerate(p.all_prompts):      # for each image in batch

            inserted_prompt = "ALİ HAYDAR GÜLEÇ" + text_to_be_sent

            if inserted_prompt:
                p.all_prompts[i] = inserted_prompt + ", " + prompt

    def after_component(self, component, **kwargs):
        # https://github.com/AUTOMATIC1111/stable-diffusion-webui/pull/7456#issuecomment-1414465888 helpfull link
        # Find the text2img textbox component
        if kwargs.get("elem_id") == "txt2img_prompt":  # postive prompt textbox
            self.boxx = component
        # Find the img2img textbox component
        if kwargs.get("elem_id") == "img2img_prompt":  # postive prompt textbox
            self.boxxIMG = component

        # this code below  works aswell, you can send negative prompt text box,provided you change the code a little
        # switch  self.boxx with  self.neg_prompt_boxTXT  and self.boxxIMG with self.neg_prompt_boxIMG

        # if kwargs.get("elem_id") == "txt2img_neg_prompt":
            #self.neg_prompt_boxTXT = component
        # if kwargs.get("elem_id") == "img2img_neg_prompt":
            #self.neg_prompt_boxIMG = component
