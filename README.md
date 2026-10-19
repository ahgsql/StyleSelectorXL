# 新舊版本差異比較

## 一、核心架構差異

| 項目 | 舊版 (`StyleSelectorXL_1.0`) | 新版 (`StyleSelectorXL_2.0`) |
|------|-------------------------------|------------------------|
| 風格檔來源 | 固定讀取 `nsfw_styles.json` | 動態讀取 `ALL.json`，並可上傳替換 |
| 檔案格式 | 只支援 `.json` | 支援 `.json`、`.xlsx`、`.xls` |
| Prompt 注入時機 | `process()` 直接改寫 `p.all_prompts` | 延後到 `process_batch()` 才寫入（避免被 wildcard 等擴充覆蓋） |
| 分類系統 | 無 | 新增 Category 1~4，可過濾風格 |
| 顯示語言 | 無 | 新增 name / namezh / namejp / nameen 切換 |
| Random Select | 每次呼叫各自隨機 | 先 `resolve_style_name()` 抽一次，正負向共用同一個結果 |

---

## 二、新增功能

### 1. Excel 支援 + openpyxl 修補
- 新增 `read_xlsx_as_style_list()`：讀取 Excel 第一個工作表，欄位需含 `name`、`prompt`，選填 `negative_prompt`、`category`、`namezh`、`namejp`、`nameen`。
- 新增 `_patch_openpyxl_extLst()`：修補 WPS / LibreOffice 產生的 xlsx 常見的 `<extLst>` 解析錯誤。

### 2. Category 分類系統
- `split_categories()` / `get_all_categories()` / `filter_styles_by_category()`
- 支援逗號分隔多分類，例如 `"medieval fantasy,衣服,配件"`。
- UI 上每個風格槽位（style1~4）對應一個 Category 下拉選單，切換 category 時該 style 下拉只顯示對應風格並重置為 `base`。

### 3. 多語言顯示
- `DISPLAY_FIELD_CHOICES`：name / 中文 / 日本語 / English。
- `display_lang.change` 事件會重建 style 下拉的顯示文字，但 value 永遠是 canonical `name`，不影響後端邏輯。

### 4. AllStyles 模式強化
- 若使用者有指定分類，只在該分類內依序生成；若無指定則跑全部風格。
- 用 `seen` set 去重、排序。

### 5. `process_batch()` 延後注入
- 舊版在 `process()` 直接改 `p.all_prompts`，但其他 AlwaysVisible 擴充（例如 wildcard 解析）若在其後執行，會用第一張 prompt 當範本重新產生整批，導致每張風格被覆蓋成同一個。
- 新版把注入延後到 `process_batch()`，保證在所有擴充的 `process()` 都跑完、wildcard 都解析完之後才寫入，並同步更新 `p.all_prompts` 與 `p.all_negative_prompts`。

### 6. `Random Select` 一致性
- 舊版：`createPositive` 與 `createNegative` 各自隨機抽一次，可能正負向對應不同風格。
- 新版：先 `resolve_style_name()` 抽一次，正負向共用同一個實際 style。

### 7. 檔案管理
- 上傳檔案時同步更新 `StyleSelectorXL.styleNames`，避免 AllStyles 模式仍用舊清單。
- 上傳成功會重建 category 清單與 style 下拉。
- 副檔名檢查（`.json` / `.xlsx` / `.xls`）。

### 8. 其他修正
- `createPositive` / `createNegative` 對 `None`、非字串做防護。
- `copy_styles_to_prompt_func` 重置時把 style choices 恢復成「全部風格」。
- UI 元件順序與 `process()` 參數順序對齊（新增 cat1~4）。
- 使用 `BASE_DIR` 推算擴充根目錄，不再依賴 `scripts.basedir()`。

---

# GitHub 更新說明（Release Notes）

## 🎉 Style Selector for SDXL 1.0 — 重大更新

本次更新大幅強化了風格管理與批次生成的正確性，新增 Excel 支援、分類系統與多語言顯示。

### ✨ 新功能

- **Excel 支援**：現在可以直接上傳 `.xlsx` / `.xls` 風格檔，不限於 JSON。
  - 第一列需為欄位標題，至少包含 `name` 與 `prompt`
  - 選填欄位：`negative_prompt`、`category`、`namezh`、`namejp`、`nameen`
  - 已修補 WPS / LibreOffice 產生的 xlsx 常見 `<extLst>` 解析錯誤

- **Category 分類系統**：每個風格槽位可獨立選擇 Category，只顯示該分類的風格。
  - 支援逗號分隔多分類（例如 `medieval fantasy,衣服,配件`）
  - 切換 Category 時對應的風格下拉會自動過濾並重置為 `base`

- **多語言顯示**：風格下拉可切換顯示 `name` / `中文` / `日本語` / `English`。
  - 顯示文字可切換，實際傳回的 value 永遠是 canonical `name`，不影響生成邏輯

- **AllStyles 模式強化**：若指定了分類，只在該分類內依序生成；未指定則跑全部風格。

### 🐛 重要修正

- **修正批次生成風格被覆蓋的問題**：風格注入延後到 `process_batch()` 執行，確保在所有擴充套件（含 wildcard 解析）的 `process()` 都跑完之後才寫入 prompt，避免每張圖的風格被覆蓋成同一個。

- **修正 `Random Select` 正負向不一致**：現在會先抽一次實際風格，正負向共用同一個結果。

- **修正上傳檔案後 AllStyles 模式仍用舊清單**：上傳時同步更新 `StyleSelectorXL.styleNames`。

- **修正複製風格後下拉選單卡在舊分類**：重置時將 style choices 恢復成「全部風格」。

- **穩定性強化**：`createPositive` / `createNegative` 對 `None` 與非字串輸入做防護。

### 🔧 其他變更

- 風格檔預設改為 `ALL.json`（位於擴充根目錄）
- 使用 `BASE_DIR` 推算路徑，不再依賴 `scripts.basedir()`
- UI 元件與 `process()` 參數順序對齊（新增 `cat1`~`cat4`）
- 檔案上傳支援 `.json` / `.xlsx` / `.xls`，並顯示載入的風格數量

### ⚠️ 注意事項

- 讀取 Excel 需要 `openpyxl`，請先執行：
  ```
  pip install openpyxl
  ```
- 舊版使用 `nsfw_styles.json`，新版預設讀取 `ALL.json`，請將既有風格檔更名或上傳替換。

### 📁 風格檔位置（2.1）

- 程式優先讀取擴充根目錄的 `ALL.json`；找不到時改讀 repo 內附的 `ALL.example.json`（13 筆範例）。
- `ALL.json` 是個人樣式表，已列入 `.gitignore`，不會被推到 GitHub。要開始自訂時，把 `ALL.example.json` 複製一份改名為 `ALL.json` 再編輯。
- 樣式表的 Excel 原始檔（`*.xlsx`）同樣只放在本機。
- `SKILL_Danbooru_CSV_Row_Completer_v1.5.txt`：用 LLM 把 name / prompt 補齊成七欄樣式資料（輸出 TSV，可直接貼進 Excel）。

---

**完整變更**：1.0 → 2.0

感謝所有使用者的回饋與測試！


## Style Selector for SDXL 1.0
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/ahgsql)

This repository contains a Automatic1111 Extension allows users to select and apply different styles to their inputs using SDXL 1.0.

### Styles

Released positive and negative templates are used to generate stylized prompts. Just install extension, then SDXL Styles will appear in the panel.

### Installation

Enter this repo's URL in Automatic1111's extension tab "Install from Url":

https://github.com/ahgsql/StyleSelectorXL.git

### Usage

Enable or Disable it On Extension's panel, Write your subject into Prompt field,
Select Style then hit Generate!
The selected style will be applied to your current prompts.

### Thanks

Huge thanks for https://github.com/twri/sdxl_prompt_styler as i got style json file's original structure from his repo.

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
