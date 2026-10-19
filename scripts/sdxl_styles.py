import contextlib
import gradio as gr
from modules import scripts, shared, script_callbacks
from modules.ui_components import FormRow, FormColumn, FormGroup, ToolButton
import json
import os
import random
import re
import subprocess
import platform

# ---- 修補 openpyxl：忽略 <extLst>（WPS/LibreOffice 產生的 xlsx 常見） ----
def _patch_openpyxl_extLst():
    try:
        from openpyxl.styles.fills import PatternFill
    except Exception:
        return
    if getattr(PatternFill, "_extLst_patched", False):
        return

    orig = getattr(PatternFill, "_from_tree", None)
    if orig is None:
        return
    orig_func = getattr(orig, "__func__", orig)

    def _from_tree(cls, node):
        # 移除不認得的屬性（例如 extLst="1"）
        for key in list(node.attrib):
            if key.split(":")[-1] == "extLst":
                del node.attrib[key]
        # 移除不認得的子節點 <extLst>...</extLst>
        for child in list(node):
            if child.tag.split("}")[-1] == "extLst":
                node.remove(child)
        return orig_func(cls, node)

    PatternFill._from_tree = classmethod(_from_tree)
    PatternFill._extLst_patched = True


_patch_openpyxl_extLst()

stylespath = ""
# 取得當前 py 檔所在目錄，並推算出擴充功能根目錄
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 個人樣式表 ALL.json 不放進 git；找不到時改用 repo 內附的範例 ALL.example.json
STYLE_FILE_CANDIDATES = ("ALL.json", "ALL.example.json")


def default_styles_path():
    for name in STYLE_FILE_CANDIDATES:
        path = os.path.join(BASE_DIR, name)
        if os.path.exists(path):
            return path
    return os.path.join(BASE_DIR, STYLE_FILE_CANDIDATES[0])


def get_json_content(file_path):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".xlsx", ".xls"):
            return read_xlsx_as_style_list(file_path)
        with open(file_path, 'rt', encoding="utf-8-sig") as file:
            json_data = json.load(file)
            return json_data
    except Exception as e:
        print(f"A Problem occurred: {str(e)}")
        return None


def read_xlsx_as_style_list(file_path):
    """讀取 Excel（.xlsx/.xls）樣式檔案，轉成跟 ALL.json 一樣的 list[dict] 結構，
    這樣其他所有邏輯（category 篩選、Random Select、createPositive/Negative...）都不用改。

    Excel 規則：
      - 只讀第一個工作表
      - 第一列必須是欄位標題（header），至少要有 'name' 和 'prompt' 兩欄（大小寫不拘）
      - 'negative_prompt'、'category'、'namezh'、'namejp' 為選填欄位，沒有就略過
      - name 是空白的列會被跳過（可用來分隔/註解）
    """
    try:
        import openpyxl
    except ImportError:
        print("Error: 讀取 Excel 需要 openpyxl 套件，請先執行「pip install openpyxl」")
        return None

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as e:
        print(f"Error reading xlsx file: {e}")
        return None

    if not rows:
        return []

    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]

    if "name" not in header or "prompt" not in header:
        print("Error: Excel 檔案缺少必要欄位 'name' 或 'prompt'（請確認第一列是欄位標題）")
        return None

    col = {key: header.index(key) for key in
           ("name", "prompt", "negative_prompt", "category", "namezh", "namejp", "nameen") if key in header}

    def cell(row, key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return None
        value = row[idx]
        return str(value).strip() if value is not None else None

    styles = []
    for row in rows[1:]:
        if row is None or all(c is None for c in row):
            continue  # 跳過整列空白
        name = cell(row, "name")
        if not name:
            continue  # 沒有 name 的列跳過

        item = {
            "name": name,
            "prompt": cell(row, "prompt") or "",
            "negative_prompt": cell(row, "negative_prompt") or "",
        }
        for optional_key in ("category", "namezh", "namejp", "nameen"):
            value = cell(row, optional_key)
            if value:
                item[optional_key] = value
        styles.append(item)

    return styles


def read_sdxl_styles(json_data):
    if not isinstance(json_data, list):
        print("Error: input data must be a list")
        return None

    names = [item['name'] for item in json_data if isinstance(item, dict) and 'name' in item]
    names.sort()
    names.insert(0, "base")
    names.insert(1, "Random Select")
    return names


def split_categories(cat_str):
    """把 'medieval fantasy,衣服,配件' 這種字串拆成獨立 category 列表"""
    if not cat_str or not isinstance(cat_str, str):
        return []
    return [c.strip() for c in cat_str.split(",") if c.strip()]


def get_all_categories(json_data):
    """从 JSON 数据中提取所有不重复的 category（支援逗號分隔多值）"""
    if not isinstance(json_data, list):
        return []
    categories = set()
    for item in json_data:
        if isinstance(item, dict) and "category" in item:
            for c in split_categories(item["category"]):
                categories.add(c)
    return sorted(list(categories))


def filter_styles_by_category(json_data, category):
    """根据 category 过滤样式列表。
    - category 为 'ALL' 或空 → 返回全部
    - 否則只要該 item 的 category 欄位（可為逗號分隔多值）中「包含」所選 category 就納入
    """
    if category == "ALL" or not category:
        return json_data
    result = []
    for item in json_data:
        if not isinstance(item, dict):
            continue
        item_cats = split_categories(item.get("category", ""))
        if category in item_cats:
            result.append(item)
    return result


DISPLAY_FIELD_CHOICES = [
    ("name", "name"),
    ("中文", "namezh"),
    ("日本語", "namejp"),
    ("English", "nameen"),
]
DISPLAY_FIELD_KEYS = [key for _, key in DISPLAY_FIELD_CHOICES]


def build_choice_label(item, display_field):
    """依 display_field 取得要顯示在下拉選單的文字；該欄位不存在或空白時 fallback 回 name。"""
    if display_field and display_field != "name":
        value = item.get(display_field)
        if value and str(value).strip():
            return str(value).strip()
    return str(item.get("name", "")).strip()


def get_style_choices_by_category(category, display_field="name"):
    """依 category 從目前的 stylespath JSON 過濾出風格清單，
    回傳 (顯示文字, 實際 name) 的 tuple 清單，供下拉選單 choices 使用。
    顯示文字依 display_field 決定（name/namezh/namejp/nameen...），
    實際傳回的 value 永遠是 canonical 的 'name'，後端邏輯完全不受影響。"""
    json_data = get_json_content(stylespath)
    base_choices = [("base", "base"), ("Random Select", "Random Select")]
    if not isinstance(json_data, list):
        return base_choices
    filtered = filter_styles_by_category(json_data, category)
    entries = [
        (build_choice_label(item, display_field), item['name'])
        for item in filtered if isinstance(item, dict) and 'name' in item
    ]
    entries.sort(key=lambda t: t[0])
    return base_choices + entries


def on_category_change(category, display_field="name"):
    """cat1~cat4 change 事件共用函式：更新對應 styleN 的 choices 並重置為 base。"""
    new_choices = get_style_choices_by_category(category, display_field)
    return gr.Dropdown.update(choices=new_choices, value='base')


def on_language_change(display_field, cat1, cat2, cat3, cat4):
    """顯示語言切換事件：重新產生 style1~4 的 choices，但不重置目前選到的值
    （因為 value 永遠是 canonical name，沒有變動，只是顯示文字換了）。"""
    return (
        gr.Dropdown.update(choices=get_style_choices_by_category(cat1, display_field)),
        gr.Dropdown.update(choices=get_style_choices_by_category(cat2, display_field)),
        gr.Dropdown.update(choices=get_style_choices_by_category(cat3, display_field)),
        gr.Dropdown.update(choices=get_style_choices_by_category(cat4, display_field)),
    )


def getStyles():
    global stylespath
    json_path = default_styles_path()
    stylespath = json_path
    file_name = os.path.basename(json_path)

    if not os.path.exists(json_path):
        print(f"Warning: {file_name} not found, using default 'base' only.")
        return ["base", "Random Select"]

    json_data = get_json_content(json_path)
    if json_data is None:
        print(f"Warning: Failed to parse {file_name}, using default 'base' only.")
        return ["base", "Random Select"]

    result = read_sdxl_styles(json_data)
    return result if result is not None else ["base", "Random Select"]


def resolve_style_name(style, category="ALL"):
    """若 style 為 Random Select，依 category 隨機抽一個實際 style name 並回傳；否則原樣回傳。"""
    if style != "Random Select":
        return style
    json_data = get_json_content(stylespath)
    if not isinstance(json_data, list):
        return style
    filtered = filter_styles_by_category(json_data, category)
    available_styles = [item['name'] for item in filtered if isinstance(item, dict) and 'name' in item]
    if available_styles:
        return random.choice(available_styles)
    return style


_BRACE_PATTERN = re.compile(r'\{([^{}]*)\}')


def _resolve_single_brace(inner):
    """解析單一一層 {...} 的內容，支援：
    - {A|B|C}                 -> 隨機選 1 個
    - {2$$A|B|C}              -> 隨機選固定 2 個，用預設分隔符 ', ' 接起來
    - {1-2$$A|B|C}            -> 隨機選 1~2 個
    - {1-2$$ and $$A|B|C}     -> 自訂分隔符 ' and '
    - 選項可帶權重前綴 '2::文字'，權重會被忽略（只當作一般選項，不影響機率）
    這只是 sd-dynamic-prompts 語法的一個簡化子集，滿足常見用法即可。
    """
    body = inner
    min_n = max_n = 1
    sep = ', '

    m = re.match(r'^\s*(\d+)(?:-(\d+))?\$\$(.*)$', inner, re.S)
    if m:
        min_n = int(m.group(1))
        max_n = int(m.group(2)) if m.group(2) else min_n
        rest = m.group(3)
        sep_match = re.match(r'^([^$]*)\$\$(.*)$', rest, re.S)
        if sep_match:
            sep = sep_match.group(1)
            body = sep_match.group(2)
        else:
            body = rest

    options = [opt.strip() for opt in body.split('|')]
    cleaned = []
    for opt in options:
        wm = re.match(r'^\s*[\d.]+::(.*)$', opt, re.S)
        cleaned.append(wm.group(1).strip() if wm else opt)
    options = [o for o in cleaned if o != ""]

    if not options:
        return ""

    if max_n < min_n:
        max_n = min_n
    n = random.randint(min_n, max_n)
    n = max(0, min(n, len(options)))
    if n == 0:
        return ""

    chosen = random.sample(options, n)
    return sep.join(chosen)


def resolve_dynamic_syntax(text, _max_passes=25):
    """反覆解析字串中的 {A|B}、{1-2$$A|B|C} 語法，支援巢狀（由內往外一層一層展開）。
    這是專門補給「風格範本注入」用的：因為這段文字是在 process_batch() 才被
    寫進 prompt，Dynamic Prompts 擴充套件當時已經解析完一輪、不會再處理它，
    所以風格範本裡若含有這類語法，要在這裡自己展開，否則會原封不動送進最終 prompt。"""
    if not text:
        return text
    result = text
    for _ in range(_max_passes):
        new_result, count = _BRACE_PATTERN.subn(
            lambda m: _resolve_single_brace(m.group(1)), result)
        if count == 0:
            break
        result = new_result
    return result


def createPositive(style, positive, category="ALL"):
    """style 應已是實際名稱（Random Select 請先用 resolve_style_name 解析）。"""
    json_data = get_json_content(stylespath)
    try:
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        # 相容：若仍傳入 Random Select，在此解析一次
        if style == "Random Select":
            style = resolve_style_name(style, category)
            if style == "Random Select":
                return str(positive) if positive is not None else ""

        for template in json_data:
            if template.get('name') == style:
                prompt = template.get('prompt', "")
                if prompt is None:
                    prompt = ""
                else:
                    prompt = str(prompt)
                merged = prompt.replace('{prompt}', str(positive) if positive is not None else "")
                return resolve_dynamic_syntax(merged)

        raise ValueError(f"No template found with name '{style}'.")
    except Exception as e:
        print(f"An error occurred in createPositive: {str(e)}")
        return str(positive) if positive is not None else ""


def createNegative(style, negative, category="ALL"):
    """style 應已是實際名稱（Random Select 請先用 resolve_style_name 解析）。"""
    json_data = get_json_content(stylespath)
    try:
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        if style == "Random Select":
            style = resolve_style_name(style, category)
            if style == "Random Select":
                return str(negative) if negative is not None else ""

        for template in json_data:
            if template.get('name') == style:
                json_negative_prompt = template.get('negative_prompt', "")
                if json_negative_prompt is None:
                    json_negative_prompt = ""
                else:
                    json_negative_prompt = str(json_negative_prompt)
                json_negative_prompt = resolve_dynamic_syntax(json_negative_prompt)
                neg_str = str(negative) if negative is not None else ""

                if json_negative_prompt and neg_str:
                    return f"{json_negative_prompt}, {neg_str}"
                elif json_negative_prompt:
                    return json_negative_prompt
                else:
                    return neg_str

        raise ValueError(f"No template found with name '{style}'.")
    except Exception as e:
        print(f"An error occurred in createNegative: {str(e)}")
        return str(negative) if negative is not None else ""


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


def process_uploaded_json(file_obj):
    global stylespath

    if file_obj is None:
        return None, None, "No file uploaded"

    try:
        if hasattr(file_obj, 'name'):
            file_path = file_obj.name
        else:
            file_path = str(file_obj)

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in (".json", ".xlsx", ".xls"):
            return None, None, f"Unsupported file type '{ext}'. Please upload a .json or .xlsx file."

        json_data = get_json_content(file_path)
        if not json_data:
            return None, None, f"Failed to parse style file: {os.path.basename(file_path)}"

        new_styles = read_sdxl_styles(json_data)
        if not new_styles:
            return None, None, f"Invalid style list in: {os.path.basename(file_path)}"

        stylespath = file_path
        filename = os.path.basename(file_path)
        return new_styles, filename, f"Successfully loaded: {filename} ({len(json_data)} styles)"

    except Exception as e:
        print(f"Error processing uploaded file: {e}")
        return None, None, f"Error processing file: {str(e)}"


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


def update_styles_from_uploaded_file(file_obj, display_field="name"):
    new_styles, filename, status = process_uploaded_json(file_obj)

    if new_styles:
        # 同步更新 class 變數，避免「Generate All Styles In Order」模式仍用舊清單
        StyleSelectorXL.styleNames = new_styles
        # 更新样式下拉框（依目前選擇的顯示語言重建 label）
        style_update = gr.Dropdown.update(choices=get_style_choices_by_category("ALL", display_field), value='base')
        # 读取 JSON 获取类别列表
        json_data = get_json_content(stylespath)
        categories = ["ALL"] + get_all_categories(json_data) if json_data else ["ALL"]
        cat_update = gr.Dropdown.update(choices=categories, value='ALL')
        return (
            style_update, style_update, style_update, style_update,  # style1~4
            cat_update, cat_update, cat_update, cat_update,          # cat1~4
            filename or "Unknown file",
            status or "File upload failed"
        )
    else:
        # 失败时只更新状态，下拉框不变
        return (
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(),
            status or "File upload failed"
        )


def copy_styles_to_prompt_func(current_prompt, current_neg_prompt,
                               style1, style2, style3, style4,
                               cat1, cat2, cat3, cat4,
                               display_field="name"):
    current_prompt = current_prompt or ""
    current_neg_prompt = current_neg_prompt or ""

    # 重置 style1~4 時，choices 要恢復成「全部風格」（category = ALL），
    # 否則畫面上 cat 顯示 ALL，但 style 選單仍卡在切換前的分類過濾結果
    full_style_choices = get_style_choices_by_category("ALL", display_field)
    style_reset = gr.Dropdown.update(choices=full_style_choices, value='base')

    # 组合样式和类别
    styles_with_cats = [(style1, cat1), (style2, cat2), (style3, cat3), (style4, cat4)]
    selected = [(s, c) for s, c in styles_with_cats if s and s != 'base']

    if not selected:
        return (current_prompt, current_neg_prompt,
                style_reset, style_reset, style_reset, style_reset,
                'ALL', 'ALL', 'ALL', 'ALL')

    positive_styles = []
    negative_styles = []

    for style, cat in selected:
        try:
            # 先 resolve 一次，正負向共用同一個實際 style
            actual = resolve_style_name(style, cat)
            pos_style = createPositive(actual, "", cat)
            neg_style = createNegative(actual, "", cat)

            if pos_style and isinstance(pos_style, str) and pos_style.strip():
                positive_styles.append(pos_style.strip())
            if neg_style and isinstance(neg_style, str) and neg_style.strip():
                negative_styles.append(neg_style.strip())
        except Exception as e:
            print(f"Error processing style {style}: {e}")
            continue

    new_prompt = current_prompt
    if positive_styles:
        style_text = ", ".join(positive_styles)
        if current_prompt.strip():
            new_prompt = f"{current_prompt}, {style_text}"
        else:
            new_prompt = style_text

    new_neg_prompt = current_neg_prompt
    if negative_styles:
        style_text = ", ".join(negative_styles)
        if current_neg_prompt.strip():
            new_neg_prompt = f"{current_neg_prompt}, {style_text}"
        else:
            new_neg_prompt = style_text

    # 重置下拉框为 base 和 ALL（style 選項也一併恢復成全部風格）
    return (new_prompt, new_neg_prompt,
            style_reset, style_reset, style_reset, style_reset,
            'ALL', 'ALL', 'ALL', 'ALL')


def add_to_main_prompt_func(current_prompt, current_neg_prompt, style_at_beginning):
    return f"Ready to add to main prompt:\nPositive: {current_prompt}\nNegative: {current_neg_prompt}\nPosition: {'Beginning' if style_at_beginning else 'End'}"


class StyleSelectorXL(scripts.Script):
    styleNames = []

    def __init__(self) -> None:
        super().__init__()
        if not StyleSelectorXL.styleNames:
            StyleSelectorXL.styleNames = getStyles()
        self.styleNames = StyleSelectorXL.styleNames

    def title(self):
        return "Style Selector for SDXL 1.0"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        enabled = getattr(shared.opts, "enable_styleselector_by_default", True)

        # 读取当前 JSON 获取类别列表（初始）
        json_data = get_json_content(stylespath)
        categories = ["ALL"] + get_all_categories(json_data) if json_data else ["ALL"]

        with gr.Group():
            with gr.Accordion("SDXL Styles", open=False):
                with FormRow():
                    with FormColumn(min_width=160):
                        is_enabled = gr.Checkbox(value=enabled, label="Enable Style Selector")
                    with FormColumn(elem_id="Style At Beginning"):
                        style_at_beginning = gr.Checkbox(value=False, label="Place Style At Beginning")

                with FormRow():
                    with FormColumn(min_width=160):
                        allstyles = gr.Checkbox(value=False, label="Generate All Styles In Order")
                with FormRow():
                    with FormColumn(min_width=240):
                        display_lang = gr.Radio(choices=DISPLAY_FIELD_CHOICES, value="name",
                                                 label="模版風格顯示語言 (Display Field)")

                # Style 1 ~ 4 与 Category 1 ~ 4 配对（各自獨立）
                with FormRow():
                    with FormColumn(min_width=160):
                        cat1 = gr.Dropdown(choices=categories, value='ALL', multiselect=False, label="Random Category 1")
                        style1 = gr.Dropdown(get_style_choices_by_category('ALL', 'name'), value='base', multiselect=False, label="模版風格 1")
                    with FormColumn(min_width=160):
                        cat2 = gr.Dropdown(choices=categories, value='ALL', multiselect=False, label="Random Category 2")
                        style2 = gr.Dropdown(get_style_choices_by_category('ALL', 'name'), value='base', multiselect=False, label="模版風格 2")
                    with FormColumn(min_width=160):
                        cat3 = gr.Dropdown(choices=categories, value='ALL', multiselect=False, label="Random Category 3")
                        style3 = gr.Dropdown(get_style_choices_by_category('ALL', 'name'), value='base', multiselect=False, label="模版風格 3")
                    with FormColumn(min_width=160):
                        cat4 = gr.Dropdown(choices=categories, value='ALL', multiselect=False, label="Random Category 4")
                        style4 = gr.Dropdown(get_style_choices_by_category('ALL', 'name'), value='base', multiselect=False, label="模版風格 4")

                # Category 切換時，對應的 style 下拉選單只顯示該分類的風格（並重置為 base）
                cat1.change(fn=on_category_change, inputs=[cat1, display_lang], outputs=[style1])
                cat2.change(fn=on_category_change, inputs=[cat2, display_lang], outputs=[style2])
                cat3.change(fn=on_category_change, inputs=[cat3, display_lang], outputs=[style3])
                cat4.change(fn=on_category_change, inputs=[cat4, display_lang], outputs=[style4])

                # 顯示語言切換時，重新產生 style1~4 的 label（保留目前選到的 style，不重置）
                display_lang.change(fn=on_language_change,
                                     inputs=[display_lang, cat1, cat2, cat3, cat4],
                                     outputs=[style1, style2, style3, style4])

                gr.Markdown("### Style File Management")
                with FormRow():
                    with FormColumn(min_width=300):
                        json_file_upload = gr.File(
                            label="Upload Style File (JSON or Excel)",
                            file_types=[".json", ".xlsx", ".xls"],
                            file_count="single"
                        )
                    with FormColumn(min_width=200):
                        open_button = gr.Button(value="Open Current Style File", variant="secondary")
                    with FormColumn():
                        file_status = gr.Textbox(label="Current File", value=os.path.basename(stylespath or default_styles_path()), interactive=False)

                with FormRow():
                    upload_status = gr.Textbox(label="Upload Status", lines=1, interactive=False)

                gr.Markdown("### Copy Styles to Prompt")
                with FormRow():
                    with FormColumn():
                        prompt_preview = gr.Textbox(label="Current Prompt", placeholder="Enter your prompt here", lines=2)
                    with FormColumn():
                        neg_prompt_preview = gr.Textbox(label="Current Negative Prompt", placeholder="Enter your negative prompt here", lines=2)

                with FormRow():
                    with FormColumn(min_width=160):
                        use_current_prompt = gr.Checkbox(value=False, label="Use Current Prompt as Style")
                    with FormColumn(min_width=200):
                        copy_styles_button = gr.Button(value="Copy Styles to Prompt & Reset to Base", variant="secondary")
                    with FormColumn(min_width=200):
                        add_to_main_button = gr.Button(value="Add to Main Prompt", variant="primary")

                with FormRow():
                    status_display = gr.Textbox(label="Status", lines=3, interactive=False)

                # 文件上传事件 - 更新所有下拉框
                json_file_upload.change(
                    fn=update_styles_from_uploaded_file,
                    inputs=[json_file_upload, display_lang],
                    outputs=[style1, style2, style3, style4,
                             cat1, cat2, cat3, cat4,
                             file_status, upload_status]
                )

                open_button.click(
                    fn=lambda: open_json_file(),
                    inputs=[],
                    outputs=[]
                )

                # 复制样式按钮 - 传入 style 和 cat
                copy_styles_button.click(
                    fn=copy_styles_to_prompt_func,
                    inputs=[prompt_preview, neg_prompt_preview,
                            style1, style2, style3, style4,
                            cat1, cat2, cat3, cat4,
                            display_lang],
                    outputs=[prompt_preview, neg_prompt_preview,
                             style1, style2, style3, style4,
                             cat1, cat2, cat3, cat4]
                )

                add_to_main_button.click(
                    fn=add_to_main_prompt_func,
                    inputs=[prompt_preview, neg_prompt_preview, style_at_beginning],
                    outputs=[status_display]
                )

                add_to_main_button.click(
                    fn=None,
                    inputs=[prompt_preview, neg_prompt_preview, style_at_beginning],
                    outputs=[],
                    _js="""
                    function(current_prompt, current_neg_prompt, at_beginning) {
                        const mainPromptInput = document.querySelector('#txt2img_prompt textarea, #img2img_prompt textarea');
                        const mainNegPromptInput = document.querySelector('#txt2img_neg_prompt textarea, #img2img_neg_prompt textarea');
                        
                        function appendText(input, text, atBeginning) {
                            if (!input || !text || !text.trim()) return;
                            const current = input.value || '';
                            const trimmed = text.trim();
                            if (atBeginning) {
                                input.value = trimmed + (current ? ', ' + current : '');
                            } else {
                                input.value = current + (current ? ', ' : '') + trimmed;
                            }
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                        
                        appendText(mainPromptInput, current_prompt, at_beginning);
                        appendText(mainNegPromptInput, current_neg_prompt, at_beginning);
                        return [];
                    }
                    """
                )

        # 注意：返回的组件顺序必须与 process 函数的参数顺序一致
        return [is_enabled, allstyles, style_at_beginning, use_current_prompt,
                prompt_preview, neg_prompt_preview,
                style1, style2, style3, style4,
                cat1, cat2, cat3, cat4,
                file_status, upload_status]

    @staticmethod
    def _auto_expand_batch(p, needed):
        """AllStyles 模式：自動把 Batch count 設成「風格數量」，不需使用者手動填。
        此時 p.all_prompts / all_seeds 等已經依原本的 n_iter 建好，所以要一併擴充。"""
        batch_size = max(1, int(getattr(p, "batch_size", 1) or 1))
        new_n_iter = max(1, -(-needed // batch_size))  # ceil
        total = new_n_iter * batch_size
        cur = len(p.all_prompts)
        if total == cur and p.n_iter == new_n_iter:
            return
        p.n_iter = new_n_iter

        def _fit(lst, filler):
            if lst is None:
                return lst
            lst = list(lst)
            if len(lst) > total:
                return lst[:total]
            while len(lst) < total:
                lst.append(filler(len(lst)))
            return lst

        p.all_prompts = _fit(p.all_prompts, lambda i: p.all_prompts[0])
        if getattr(p, "all_negative_prompts", None) is not None:
            base_neg = p.all_negative_prompts[0]
            p.all_negative_prompts = _fit(p.all_negative_prompts, lambda i: base_neg)
        if getattr(p, "all_seeds", None) is not None:
            base_seed = int(p.all_seeds[0])
            step_seed = 1 if getattr(p, "subseed_strength", 0) == 0 else 0
            p.all_seeds = [base_seed + (x * step_seed) for x in range(total)] \
                if len(p.all_seeds) != total and step_seed else _fit(p.all_seeds, lambda i: base_seed)
        if getattr(p, "all_subseeds", None) is not None:
            base_sub = int(p.all_subseeds[0])
            p.all_subseeds = [base_sub + x for x in range(total)] \
                if len(p.all_subseeds) != total else p.all_subseeds
        try:
            shared.state.job_count = new_n_iter
        except Exception:
            pass
        print(f"[StyleSelector] AllStyles: batch count auto-set to {new_n_iter} (batch size {batch_size}, {needed} styles)")

    def process(self, p, is_enabled, allstyles, style_at_beginning, use_current_prompt,
                current_prompt_text, current_neg_prompt_text,
                style1, style2, style3, style4,
                cat1, cat2, cat3, cat4,
                file_status, upload_status):
        # 這個 method 只負責「算出每張圖該套用哪個風格」，不直接改 p.all_prompts。
        # 原因：其他 AlwaysVisible 擴充套件（例如處理 __wildcard__ 的套件）的 process()
        # 可能在我們之後才執行，若它們用「第一張的 prompt」當範本重新產生整批 prompt，
        # 會把我們在這裡設定的、每張不同的風格覆蓋成同一個。
        # 真正把風格文字寫進 prompt 的動作延後到 process_batch()（保證在所有擴充套件的
        # process() 都執行完、wildcard 都已經解析完之後才會被呼叫）。
        self.style_selector_enabled = is_enabled
        if not is_enabled:
            return

        batchCount = len(p.all_prompts)
        # 组合样式和类别（UI 選擇）
        styles_with_cats = [(style1, cat1), (style2, cat2), (style3, cat3), (style4, cat4)]
        selected = [(s, c) for s, c in styles_with_cats if s and s != 'base']

        # AllStyles 模式：若使用者有指定分類（非 ALL），只在該分類內依序跑；
        # 若沒指定任何分類（全部都是 ALL），維持原行為跑全部風格
        allstyles_pool = []
        if allstyles:
            active_cats = sorted({c for s, c in styles_with_cats if c and c != "ALL"})
            if active_cats:
                json_data = get_json_content(stylespath)
                if isinstance(json_data, list):
                    seen = set()
                    for cat in active_cats:
                        for item in filter_styles_by_category(json_data, cat):
                            name = item.get('name')
                            if name and name not in seen:
                                seen.add(name)
                                allstyles_pool.append(name)
                    allstyles_pool.sort()
                print(f"AllStyles mode restricted to categories {active_cats}: {len(allstyles_pool)} styles")
            if not allstyles_pool:
                # 沒指定分類，或指定分類篩不到任何風格 → fallback 用全部風格
                allstyles_pool = [s for s in StyleSelectorXL.styleNames if s not in ("base", "Random Select")]

        if allstyles and allstyles_pool:
            self._auto_expand_batch(p, len(allstyles_pool))
            batchCount = len(p.all_prompts)

        # 為每一張圖解析出「實際 style name」（Random Select 只抽一次，正負向共用）
        styles_per_prompt = {}
        resolved_names_per_prompt = {}  # 記錄實際抽中的名稱，供參數顯示

        for i in range(batchCount):
            if allstyles:
                if allstyles_pool:
                    style_name = allstyles_pool[i % len(allstyles_pool)]
                    styles_per_prompt[i] = [(style_name, "ALL")]
                    resolved_names_per_prompt[i] = [style_name]
                    print(f"AllStyles mode - Image {i}: {styles_per_prompt[i]}")
                else:
                    styles_per_prompt[i] = selected
                    resolved_names_per_prompt[i] = [s for s, c in selected]
            else:
                # 每個槽位獨立 resolve：Random Select → 實際 name（只抽一次）
                resolved = []
                resolved_names = []
                for s, c in selected:
                    actual_name = resolve_style_name(s, c)
                    resolved.append((actual_name, c))
                    resolved_names.append(actual_name)
                styles_per_prompt[i] = resolved
                resolved_names_per_prompt[i] = resolved_names
                print(f"Normal mode - Image {i}: UI={selected} → resolved={resolved}")

        print(f"Total batch count: {batchCount}")
        print(f"Available style names count: {len(StyleSelectorXL.styleNames) if StyleSelectorXL.styleNames else 0}")

        # 存到 instance，供 process_batch() 使用
        self.style_selector_allstyles = allstyles
        self.style_selector_resolved_names = resolved_names_per_prompt
        self.style_selector_styles_per_prompt = styles_per_prompt
        self.style_selector_style_at_beginning = style_at_beginning
        self.style_selector_use_current_prompt = use_current_prompt
        self.style_selector_current_prompt_text = current_prompt_text
        self.style_selector_current_neg_prompt_text = current_neg_prompt_text

        # 參數顯示「實際抽中的 style name」
        # batch 時取第一張的結果作為代表（常見用法）；若要每張都不同可再擴充
        first_resolved = resolved_names_per_prompt.get(0, [])
        used_desc = []
        for idx, (s, c) in enumerate(selected):
            actual = first_resolved[idx] if idx < len(first_resolved) else s
            if s == "Random Select":
                used_desc.append(f"{actual} (from {c})" if c and c != "ALL" else actual)
            else:
                used_desc.append(actual)

        if allstyles and first_resolved:
            used_desc = list(first_resolved)

        p.extra_generation_params.update({
            "Style Selector Enabled": True,
            "Style Selector AllStyles": allstyles,
            "Style Selector At Beginning": style_at_beginning,
            "Style Selector Use Current Prompt": use_current_prompt,
            "Style Selector Styles Used": ", ".join(used_desc) if used_desc else "None"
        })

    def process_batch(self, p, is_enabled, allstyles, style_at_beginning, use_current_prompt,
                       current_prompt_text, current_neg_prompt_text,
                       style1, style2, style3, style4,
                       cat1, cat2, cat3, cat4,
                       file_status, upload_status,
                       **kwargs):
        # 這裡才是真正把風格文字寫進 prompt 的地方。process_batch() 保證會在所有
        # 擴充套件（包含處理 wildcard 的套件）的 process() 都跑完之後才被呼叫，
        # 所以這時候 prompts 裡的 wildcard 應該已經被解析成最終文字了。
        if not getattr(self, "style_selector_enabled", False):
            return

        styles_per_prompt = getattr(self, "style_selector_styles_per_prompt", None)
        if not styles_per_prompt:
            return

        prompts = kwargs.get('prompts')
        batch_number = kwargs.get('batch_number', 0)
        if prompts is None:
            return

        batch_size = len(prompts)
        start = batch_number * batch_size

        # AllStyles：每個 batch 各自更新 infotext 的「Styles Used」，
        # 讓每張圖的資訊顯示它實際套用的風格（而不是下拉選單目前的項目 / None）
        if getattr(self, "style_selector_allstyles", False):
            names = []
            resolved = getattr(self, "style_selector_resolved_names", {})
            for li in range(len(prompts)):
                for n in resolved.get(start + li, []):
                    if n not in names:
                        names.append(n)
            if names:
                p.extra_generation_params["Style Selector Styles Used"] = ", ".join(names)

        style_at_beginning = self.style_selector_style_at_beginning
        use_current_prompt = self.style_selector_use_current_prompt
        current_prompt_text = self.style_selector_current_prompt_text
        current_neg_prompt_text = self.style_selector_current_neg_prompt_text

        for local_i in range(len(prompts)):
            global_i = start + local_i
            styles = styles_per_prompt.get(global_i, [])

            # ---- 正向 ----
            original_prompt = prompts[local_i]
            injected_styles = []
            for s, c in styles:
                if s:
                    result = createPositive(s, "", c)
                    if result and isinstance(result, str):
                        injected_styles.append(result.strip())

            injection_parts = []
            style_injection = ", ".join(injected_styles)
            if style_injection:
                injection_parts.append(style_injection)
            if use_current_prompt and current_prompt_text and current_prompt_text.strip():
                injection_parts.append(current_prompt_text.strip())
            injection = ", ".join(injection_parts)

            if injection:
                if style_at_beginning:
                    prompts[local_i] = f"{injection}, {original_prompt}"
                else:
                    prompts[local_i] = f"{original_prompt}, {injection}"
                # 同步寫回主陣列 p.all_prompts —— 這個環境的實際生成/metadata 記錄
                # 讀的是 p.all_prompts，只改 process_batch 傳進來的 prompts 這個暫存清單
                # 並不會真正生效，一定要兩邊都同步更新。
                if global_i < len(p.all_prompts):
                    p.all_prompts[global_i] = prompts[local_i]
                print(f"[process_batch] Final prompt {global_i}: {prompts[local_i]}")
            else:
                print(f"[process_batch] No injection for prompt {global_i}: {original_prompt}")

            # ---- 負向 ----
            negative_prompts_local = kwargs.get('negative_prompts')
            if global_i < len(p.all_negative_prompts):
                original_neg = p.all_negative_prompts[global_i]
                injected_neg_styles = []
                for s, c in styles:
                    if s:
                        result = createNegative(s, "", c)
                        if result and isinstance(result, str):
                            injected_neg_styles.append(result.strip())

                neg_injection_parts = []
                neg_style_injection = ", ".join(injected_neg_styles)
                if neg_style_injection:
                    neg_injection_parts.append(neg_style_injection)
                if use_current_prompt and current_neg_prompt_text and current_neg_prompt_text.strip():
                    neg_injection_parts.append(current_neg_prompt_text.strip())
                neg_injection = ", ".join(neg_injection_parts)

                if neg_injection:
                    if style_at_beginning:
                        final_neg = f"{neg_injection}, {original_neg}"
                    else:
                        final_neg = f"{original_neg}, {neg_injection}"
                    p.all_negative_prompts[global_i] = final_neg
                    if negative_prompts_local is not None and local_i < len(negative_prompts_local):
                        negative_prompts_local[local_i] = final_neg
                    print(f"[process_batch] Final negative prompt {global_i}: {final_neg}")
                else:
                    print(f"[process_batch] No negative injection for prompt {global_i}: {original_neg}")


def on_ui_settings():
    section = ("styleselector", "Style Selector")
    shared.opts.add_option("styles_ui", shared.OptionInfo(
        "select-list", "How should Style Names Rendered on UI", gr.Radio, {"choices": ["radio-buttons", "select-list"]}, section=section))

    shared.opts.add_option("enable_styleselector_by_default", shared.OptionInfo(True, "Enable Style Selector by default", gr.Checkbox, section=section))


script_callbacks.on_ui_settings(on_ui_settings)
