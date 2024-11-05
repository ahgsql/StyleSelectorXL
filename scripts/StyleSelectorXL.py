import contextlib
import csv
import gradio as gr
from modules import scripts, shared, script_callbacks
from modules.ui_components import FormRow, FormColumn, FormGroup, ToolButton
import json
import os
import random

class StyleSelectorXL(scripts.Script):
  def __init__(self) -> None:
      super().__init__()
      self.style_files = self.get_style_files()
      self.selected_file = self.style_files[0] if self.style_files else None
      self.styleNames = self.get_styles(self.selected_file)

  @classmethod
  def get_style_files(cls):
      script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
      style_files = [f for f in os.listdir(script_dir) if f.endswith(('.json', '.csv'))]
      return style_files

  @staticmethod
  def get_file_content(file_path):
      try:
          file_ext = os.path.splitext(file_path)[1].lower()
          
          if file_ext == '.json':
              with open(file_path, 'rt', encoding="utf-8") as file:
                  return json.load(file)
          
          elif file_ext == '.csv':
              styles = []
              with open(file_path, 'rt', encoding='utf-8-sig') as file:
                  csv_reader = csv.DictReader(file)
                  fieldnames = csv_reader.fieldnames
                  
                  if not all(field in fieldnames for field in ['name', 'prompt', 'negative_prompt']):
                      print(f"CSV missing required columns. Found: {fieldnames}")
                      return None
                  
                  for row in csv_reader:
                      if row['name'].strip() and row['prompt'].strip():
                          style = {
                              "name": row['name'].strip(),
                              "prompt": row['prompt'].strip(),
                              "negative_prompt": row.get('negative_prompt', '').strip()
                          }
                          styles.append(style)
                          print(f"Loaded style: {style['name']}")
                  
                  return styles
              
      except Exception as e:
          print(f"Error reading {file_path}: {str(e)}")
          return None

  @staticmethod
  def read_styles(data):
      if not isinstance(data, list):
          print("Error: input data must be a list")
          return []

      names = []
      for item in data:
          if isinstance(item, dict) and 'name' in item:
              names.append(item['name'])
      names.sort()
      return names

  def get_styles(self, selected_file):
      if not selected_file:
          return []
      script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
      file_path = os.path.join(script_dir, selected_file)
      print(f"Loading styles from: {file_path}")
      file_data = self.get_file_content(file_path)
      if file_data is None:
          print("No data loaded from file")
          return []
      print(f"Loaded {len(file_data)} styles")
      styles = self.read_styles(file_data)
      print(f"Processed {len(styles)} style names")
      return styles

  def create_positive(self, style, positive, selected_file):
      script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
      file_path = os.path.join(script_dir, selected_file)
      file_data = self.get_file_content(file_path)
      try:
          if not isinstance(file_data, list):
              raise ValueError("Invalid data format. Expected a list of templates.")

          for template in file_data:
              if template['name'] == style:
                  return template['prompt'].replace('{prompt}', positive)

          raise ValueError(f"No template found with name '{style}'.")

      except Exception as e:
          print(f"Error in create_positive: {str(e)}")
          return positive

  def create_negative(self, style, negative, selected_file):
      script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
      file_path = os.path.join(script_dir, selected_file)
      file_data = self.get_file_content(file_path)
      try:
          if not isinstance(file_data, list):
              raise ValueError("Invalid data format. Expected a list of templates.")

          for template in file_data:
              if template['name'] == style:
                  style_negative = template.get('negative_prompt', '')
                  if negative:
                      return f"{style_negative}, {negative}" if style_negative else negative
                  return style_negative

          raise ValueError(f"No template found with name '{style}'.")

      except Exception as e:
          print(f"Error in create_negative: {str(e)}")
          return negative

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
                      randomize_each = gr.Checkbox(value=False, label="Randomize For Each")

              with FormRow():
                  with FormColumn(min_width=160):
                      style_count = len(self.styleNames) if self.styleNames else 0
                      all_styles = gr.Checkbox(value=False, label="Generate All Styles In Order", 
                                            info=f"To Generate Your Prompt in All Available Styles, It's Better to set batch count to {style_count} (Style Count)")

              with FormRow():
                  file_selector = gr.Dropdown(choices=self.style_files, value=self.selected_file, label="Select Style File")
                  refresh_button = ToolButton(value="\U0001f504")

              style = gr.Radio(label='Style', choices=self.styleNames, value='base' if 'base' in self.styleNames else None, type="value")

              def update_styles(file):
                  self.selected_file = file
                  self.styleNames = self.get_styles(file)
                  default_value = 'base' if 'base' in self.styleNames else (self.styleNames[0] if self.styleNames else None)
                  return gr.update(choices=self.styleNames, value=default_value)

              def refresh_files():
                  self.style_files = self.get_style_files()
                  self.selected_file = self.style_files[0] if self.style_files else None
                  self.styleNames = self.get_styles(self.selected_file)
                  default_value = 'base' if 'base' in self.styleNames else (self.styleNames[0] if self.styleNames else None)
                  return [
                      gr.update(choices=self.style_files, value=self.selected_file),
                      gr.update(choices=self.styleNames, value=default_value)
                  ]

              file_selector.change(fn=update_styles, inputs=[file_selector], outputs=[style])
              refresh_button.click(fn=refresh_files, inputs=[], outputs=[file_selector, style])

      return [is_enabled, randomize, randomize_each, all_styles, style, file_selector]

  def process(self, p, is_enabled, randomize, randomize_each, all_styles, style, selected_file):
      if not is_enabled or not self.styleNames:
          return

      if randomize:
          style = random.choice(self.styleNames)
      batch_count = len(p.all_prompts)

      if batch_count == 1:
          for i, prompt in enumerate(p.all_prompts):
              p.all_prompts[i] = self.create_positive(style, prompt, selected_file)
          for i, prompt in enumerate(p.all_negative_prompts):
              p.all_negative_prompts[i] = self.create_negative(style, prompt, selected_file)
      else:
          styles = {}
          for i in range(batch_count):
              if randomize:
                  styles[i] = random.choice(self.styleNames)
              else:
                  styles[i] = style
              if all_styles:
                  styles[i] = self.styleNames[i % len(self.styleNames)]
          
          for i, prompt in enumerate(p.all_prompts):
              current_style = styles[i] if randomize_each or all_styles else styles[0]
              p.all_prompts[i] = self.create_positive(current_style, prompt, selected_file)
          for i, prompt in enumerate(p.all_negative_prompts):
              current_style = styles[i] if randomize_each or all_styles else styles[0]
              p.all_negative_prompts[i] = self.create_negative(current_style, prompt, selected_file)

      p.extra_generation_params.update({
          "Style Selector Enabled": True,
          "Style Selector Randomize": randomize,
          "Style Selector Style": style,
          "Style Selector File": selected_file
      })

def on_ui_settings():
  section = ("styleselector", "Style Selector")
  shared.opts.add_option(
      "enable_styleselector_by_default",
      shared.OptionInfo(
          True,
          "enable Style Selector by default",
          gr.Checkbox,
          section=section
      )
  )

script_callbacks.on_ui_settings(on_ui_settings)