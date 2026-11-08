# 日文阅读拆解教练

一个面向中文日语学习者的文章知识点解析原型。输入一段日语短文，应用提取语法、词汇、句型和篇章连接，并为每个知识点保留原文引用、中文解释和练习。单篇分析默认补充语境词汇候选，目标输出至少 10 个知识点；还提供独立的“原文”标签页，完整显示带注音的原始文章。文章、知识点、引用、句子拆解和例句中的日语汉字均通过 SudachiPy 自动生成平假名，并显示在汉字上方。每个知识点同时显示 1–5 星估计考频。

## 可直接运行的部分

默认提供两种无需模型的方式：

- **演示案例**：读取 `data/samples.json` 中预存的高质量分析，适合展示产品流程。
- **规则解析**：使用本地语法模式表和词汇表识别候选知识点，不联网、不调用付费 API。
- **官方公开样题**：按 N1–N5 和官方资料版本检索 JLPT 官方公开样题链接，包括 2009 公开样题、2012/2018 官方练习册和互动样题。应用只链接官方资源，不复制或重新托管题面。

第三种 **本地模型** 模式为可选功能，默认使用 `Qwen/Qwen3-8B`，通过 Transformers 在本地显卡或 Colab 中运行。

## 本地运行

```powershell
cd C:\Users\10366\Documents\ChatGPT\娱乐\japanese-reading-coach
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

如果 `streamlit` 命令不可用，也可以：

```powershell
python -m streamlit run app.py
```

## 可选本地模型

模型依赖较重，建议在 Colab、Linux 环境或具有 GPU 的电脑上安装：

```bash
pip install -r requirements-model.txt
export JP_ANALYZER_MODEL=Qwen/Qwen3-8B
export JP_ANALYZER_4BIT=1
streamlit run app.py
```

Windows PowerShell 对应写法：

```powershell
$env:JP_ANALYZER_MODEL="Qwen/Qwen3-8B"
$env:JP_ANALYZER_4BIT="1"
streamlit run app.py
```

可选模型：

- `Qwen/Qwen3-8B`：中文解释、日语理解和 JSON 输出较均衡。
- `llm-jp/llm-jp-4-8b-instruct`：日语专门模型，适合作为日语语感备选。
- `Qwen/Qwen3-4B-Instruct-2507`：更轻量，适合低显存测试。

8B 模型使用 BF16 时通常需要约 16–18 GB 权重空间，免费 GPU 通常需要使用 4-bit 量化。

## 数据与免费演示

- `data/samples.json`：两篇合成文章及预存分析。
- `data/official_samples.json`：JLPT 官方公开样题资源目录、答案链接和版权说明链接。
- `data/grammar_patterns.json`：可解释的语法模式、估计等级和练习。
- `data/lexicon.json`：小型词汇词典。
- `src/furigana.py`：SudachiPy 分词与 HTML `<ruby>` 注音生成。

考频星级是产品中的估计字段，不应被描述为官方 JLPT 统计。数据文件和模型提示词都使用 `exam_frequency` 字段，取值为 1–5。

预估水平是严格筛选条件。支持 N4、N3、N2、N1；切换等级后会自动重新分析，并且只显示所选等级的知识点。

官方公开样题不按考试年份逐年发布，因此官方样题模式按“等级 + 官方资料版本”检索。官方题面只通过 `www.jlpt.jp` 链接打开；如需生成知识点，用户可将官方阅读正文手动粘贴到“规则解析”。

设计文档中的“数据来源与许可”应写清楚：示例文章为合成的学习材料，词典和模型的实际许可需按其官方模型卡和数据来源逐项标注。不要直接保存用户文章，除非用户明确同意。

## 目录结构

```text
app.py                       Streamlit 页面
src/schema.py                数据结构
src/text_utils.py            文本校验与句子切分
src/rule_analyzer.py         无模型规则解析
src/llm_analyzer.py          可选本地 Transformers 后端
src/prompt.py                模型提示词
src/samples.py               示例数据加载
data/                        示例、语法和词汇数据
tests/                       不依赖 Streamlit 的核心测试
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 免费部署建议

推荐结构：

1. GitHub 保存代码、提示词和示例数据。
2. Streamlit Cloud 展示界面，默认进入演示或规则模式。
3. Colab 用于测试模型和批量生成示例结果。
4. 如果 Hugging Face 账户满足 ZeroGPU 条件，可额外部署一个 Gradio 模型 Space。
5. Streamlit 的 AI 模式作为可选增强，模型不可用时仍能完成演示。

