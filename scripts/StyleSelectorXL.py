import contextlib

import gradio as gr
from modules import scripts, shared, script_callbacks
from modules.ui_components import FormRow, FormColumn, FormGroup, ToolButton
import json
import os
import random
import subprocess
import platform

stylespath = ""

def get_json_content(file_path):
    try:
        with open(file_path, 'rt', encoding="utf-8") as file:
            json_data = json.load(file)
            return json_data
    except Exception as e:
        print(f"A Problem occurred: {str(e)}")


def read_sdxl_styles(json_data):
    if not isinstance(json_data, list):
        print("Error: input data must be a list")
        return None
    
    names = [item['name'] for item in json_data if isinstance(item, dict) and 'name' in item]
    names.sort()
    return names


def getStyles():
    global stylespath
    json_path = os.path.join(scripts.basedir(), 'sdxl_styles.json')
    stylespath = json_path
    json_data = get_json_content(json_path)
    return read_sdxl_styles(json_data)


def createPositive(style, positive):
    json_data = get_json_content(stylespath)
    try:
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        for template in json_data:
            if template.get('name') == style:
                return template['prompt'].replace('{prompt}', positive)

        raise ValueError(f"No template found with name '{style}'.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")


def createNegative(style, negative):
    json_data = get_json_content(stylespath)
    try:
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        for template in json_data:
            if template.get('name') == style:
                json_negative_prompt = template.get('negative_prompt', "")
                return f"{json_negative_prompt}, {negative}" if json_negative_prompt and negative else json_negative_prompt or negative

        raise ValueError(f"No template found with name '{style}'.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        

def append_style_to_json(name, prompt, negative_prompt):
    global stylespath
    try:
        with open(stylespath, 'r+', encoding='utf-8') as f:
            styles = json.load(f)
            styles.append({
                "name": name,
                "prompt": prompt,
                "negative_prompt": negative_prompt
            })
            f.seek(0)
            json.dump(styles, f, indent=2)
            f.truncate()
    except Exception as e:
        print(f"Error saving style: {e}")

def open_json_file():
    global stylespath
    try:
        if platform.system() == "Windows":
            os.startfile(stylespath)
        elif platform.system() == "Darwin":
            subprocess.call(["open", stylespath])
        else:
            subprocess.call(["xdg-open", stylespath])
    except Exception as e:
        print(f"Could not open file: {e}")


class StyleSelectorXL(scripts.Script):
    def __init__(self) -> None:
        super().__init__()
    
    styleNames = getStyles()

    def title(self):
        return "Style Selector for SDXL 1.0"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        enabled = getattr(shared.opts, "enable_styleselector_by_default", True)
        with gr.Group():
            with gr.Accordion("SDXL Styles", open=enabled):
                with FormRow():
                    with FormColumn(min_width=160):
                        is_enabled = gr.Checkbox(value=enabled, label="Enable Style Selector")
                    with FormColumn(elem_id="Randomize Style"):
                        randomize = gr.Checkbox(value=False, label="Randomize Style")
                    with FormColumn(elem_id="Randomize For Each Iteration"):
                        randomizeEach = gr.Checkbox(value=False, label="Randomize For Each Iteration")

                with FormRow():
                    with FormColumn(min_width=160):
                        allstyles = gr.Checkbox(value=False, label="Generate All Styles In Order")

                with FormRow():
                    with FormColumn(min_width=160):
                        style1 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 1")
                    with FormColumn(min_width=160):
                        style2 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 2")
                    with FormColumn(min_width=160):
                        style3 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 3")
                    with FormColumn(min_width=160):
                        style4 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 4")
                
                with FormRow():
                    with FormColumn(min_width=160):
                        style5 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 5")
                    with FormColumn(min_width=160):
                        style6 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 6")
                    with FormColumn(min_width=160):
                        style7 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 7")
                    with FormColumn(min_width=160):
                        style8 = gr.Dropdown(self.styleNames, value='base', multiselect=False, label="Style 8")
                
                gr.Markdown("### Create New Style (Requires Restart)")
                
                with FormRow():
                    with FormColumn():
                        new_style_name = gr.Textbox(label="New Style Name:")
                        new_style_prompt = gr.Textbox(label="Positive Prompt:")
                        new_style_negative = gr.Textbox(label="Negative Prompt:")
                        
                with FormRow():
                    with FormColumn(min_width=160):
                        save_button = gr.Button(value="Save New Style")
                        save_button.click(
                            fn=lambda name, prompt, negative: (
                                append_style_to_json(name, prompt, negative),
                                "", "", ""
                            )[1:],  # Return only the empty strings
                            inputs=[new_style_name, new_style_prompt, new_style_negative],
                            outputs=[new_style_name, new_style_prompt, new_style_negative]
                        )
                    with FormColumn(min_width=160):
                        open_button = gr.Button(value="Open JSON File")
                        open_button.click(
                            fn=lambda: open_json_file(),
                            inputs=[],
                            outputs=[]
                        )

        return [is_enabled, randomize, randomizeEach, allstyles, style1, style2, style3, style4, style5, style6, style7, style8]


    def process(self, p, is_enabled, randomize, randomizeEach, allstyles, style1, style2, style3, style4, style5, style6, style7, style8):
        if not is_enabled:
            return

        batchCount = len(p.all_prompts)

        # Gather selected styles
        selected_styles = [s for s in [style1, style2, style3, style4, style5, style6, style7, style8] if s]

        # Handle randomization modes
        if randomize:
            selected_styles = random.sample(self.styleNames, k=min(3, len(self.styleNames)))

        # Generate style sets per prompt
        styles_per_prompt = {}
        for i in range(batchCount):
            if allstyles:
                # Cycle through all styles one at a time
                styles_per_prompt[i] = [self.styleNames[i % len(self.styleNames)]]
            elif randomizeEach:
                # Different styles for each prompt
                styles_per_prompt[i] = random.sample(self.styleNames, k=min(3, len(self.styleNames)))
            else:
                # Same selected styles for all prompts
                styles_per_prompt[i] = selected_styles

        # Inject positive prompts
        for i, original_prompt in enumerate(p.all_prompts):
            styles = styles_per_prompt[i]
            injected_styles = [createPositive(s, "") for s in styles]
            injection = ", ".join(injected_styles).strip(", ")
            if injection:
                p.all_prompts[i] = f"{original_prompt}, {injection}"
            else:
                p.all_prompts[i] = original_prompt

        # Inject negative prompts
        for i, original_prompt in enumerate(p.all_negative_prompts):
            styles = styles_per_prompt[i]
            injected_styles = [createNegative(s, "") for s in styles]
            injection = ", ".join(injected_styles).strip(", ")
            if injection:
                p.all_negative_prompts[i] = f"{original_prompt}, {injection}"
            else:
                p.all_negative_prompts[i] = original_prompt

        # Metadata
        p.extra_generation_params.update({
            "Style Selector Enabled": True,
            "Style Selector Randomize": randomize,
            "Style Selector RandomizeEach": randomizeEach,
            "Style Selector AllStyles": allstyles,
            "Style Selector Styles Used": ", ".join(selected_styles)
        })



def on_ui_settings():
    section = ("styleselector", "Style Selector")
    shared.opts.add_option("styles_ui", shared.OptionInfo(
        "select-list", "How should Style Names Rendered on UI", gr.Radio, {"choices": ["radio-buttons", "select-list"]}, section=section))
    
    shared.opts.add_option("enable_styleselector_by_default", shared.OptionInfo(True, "Enable Style Selector by default", gr.Checkbox, section=section))
    
script_callbacks.on_ui_settings(on_ui_settings)
