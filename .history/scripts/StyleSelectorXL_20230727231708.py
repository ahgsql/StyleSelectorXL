import contextlib

import gradio as gr
from modules import scripts
from modules import script_callbacks


def send_text_to_prompt(new_text, old_text):
    if old_text == "":  # if text on the textbox text2img or img2img is empty, return new text
        return new_text
    # else join them together and send it to the textbox
    return old_text + " " + new_text


class StyleSelectorXL(scripts.Script):
    def __init__(self) -> None:
        super().__init__()

    def title(self):
        return "Style Selector for SDXL 1.0"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Group():
            with gr.Accordion("Select Style", open=False):
                is_enabled = gr.Checkbox(
                    value=True, label="Enable CloneCleaner")
                send_text_button = gr.Button(
                    value='send text', variant='primary')
                text_to_be_sent = gr.Textbox(label="drop text")

        # Ignore the error if the attribute is not present
        with contextlib.suppress(AttributeError):
            if is_img2img:
                # Bind the click event of the button to the send_text_to_prompt function
                # Inputs: text_to_be_sent (textbox), self.boxxIMG (textbox)
                # Outputs: self.boxxIMG (textbox)
                send_text_button.click(fn=send_text_to_prompt, inputs=[
                                       text_to_be_sent, self.boxxIMG], outputs=[self.boxxIMG])
            else:
                # Bind the click event of the button to the send_text_to_prompt function
                # Inputs: text_to_be_sent (textbox), self.boxx (textbox)
                # Outputs: self.boxx (textbox)
                send_text_button.click(fn=send_text_to_prompt, inputs=[
                                       text_to_be_sent, self.boxx], outputs=[self.boxx])

        return [is_enabled, text_to_be_sent, send_text_button]

    def process(self, p, is_enabled, text_to_be_sent):
        if not is_enabled:
            return

        p.extra_generation_params["Style Selector Enabled"] = True

        for i, prompt in enumerate(p.all_prompts):      # for each image in batch
            rng = random.Random()
            seed = p.all_seeds[i] if use_main_seed else declone_seed + i
            rng.seed(seed)

            region = rng.choice(regions)
            countries = list(countrytree[region].keys())
            countryweights = [countrytree[region][cty]["weight"]
                              for cty in countries]
            country = rng.choices(countries, weights=countryweights)[0]

            countrydata = countrytree[region][country]
            hairdata = countrydata.get(
                "hair", hairtree["defaultweight"][region])
            maincolor = rng.choices(haircolors, weights=[
                                    hairdata[col] for col in haircolors])[0]
            color = rng.choice(hairtree["color"][maincolor])
            mainlength = rng.choice(hairlengths)
            length = rng.choice(hairtree["length"][mainlength])
            style = rng.choice(hairtree["style"][mainlength])
            name = rng.choice(countrydata["names"])

            inserted_prompt = ""

            if use_name or use_country:
                inserted_prompt += name if use_name else "person"
                inserted_prompt += " from " + country if use_country else ""

            if use_length or use_style or use_color:
                if inserted_prompt:
                    inserted_prompt += ", "
                if use_length:
                    inserted_prompt += length + " "
                if use_style:
                    inserted_prompt += style + " "
                if use_color:
                    inserted_prompt += color + " "
                inserted_prompt += "hair"

            if inserted_prompt:

                if insert_start:
                    p.all_prompts[i] = inserted_prompt + ", " + prompt
                else:
                    p.all_prompts[i] = prompt + ", " + inserted_prompt

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
