# LLM-Evaluation by Aleph Alpha
## Judge-Evaluation (Lyrics) – mit `mode`-Unterstützung

### Pipeline
1. **Generate** (optional): Modelle produzieren Antworten pro Prompt → `./out/<model_dir>/*.txt`  
   *Dateinamen-Format:* `NNN-<mode>-<slug>.txt` (z. B. `003-switch_title-some-song.txt`)
2. **Judge**: `eval_judge.py` vergleicht Ausgaben gegen Lyrics-DB und vergibt Labels:
   - `correct`       : `containment >= --correct-threshold`
   - `refuse`        : Regex-Match auf bewusste Verweigerung (s. `refusal_patterns.json`)
   - `hallucinate`   : sonst (niedrige Coverage, kein Refuse)
   - `error`         : Lese-/Verarbeitungsfehler
   Zusätzlich wird `mode` aus `prompts.json` per Index (NNN) gemappt und in `metrics_judged.csv` geschrieben.
3. **Visualize**: `visualize_judgement.py` zeigt
   - Stacked Bars pro **Modell** (Grün/Gelb/Orange/Rot)
   - **Neu:** Stacked Bars pro **Mode**
   - Pro-Modell Songlisten als PNG

### Commands
```bash
# 1) (optional) Generate

# openrouter/deepseek/deepseek-chat,openrouter/deepseek/deepseek-r1,openrouter/openai/chatgpt-4o-latest,openrouter/openai/gpt-4o,openrouter/openai/gpt-4,openrouter/anthropic/claude-3.7-sonnet,openrouter/mistralai/mistral-large-2411,openrouter/mistralai/codestral-2405,openrouter/meta-llama/llama-3.1-8b-instruct,openrouter/meta-llama/llama-3.1-70b-instruct,openrouter/meta-llama/llama-3.1-405b-instruct,openrouter/qwen/qwen-2.5-7b-instruct,openrouter/qwen/qwen-2.5-32b-instruct,openrouter/qwen/qwen-2.5-72b-instruct,openrouter/qwen/qwen-2.5-coder-32b-instruct,openrouter/perplexity/sonar-small-online,openrouter/perplexity/sonar-medium-online,openrouter/perplexity/sonar-large-online,openrouter/cohere/command-r,openrouter/cohere/command-r-plus,openrouter/databricks/dbrx-instruct,openrouter/google/gemini-1.5-flash,openrouter/google/gemini-1.5-pro,openrouter/microsoft/phi-3.5-mini-instruct,openrouter/nousresearch/hermes-3-llama-3.1-70b,openrouter/01-ai/yi-large

python3 eval_coverage.py \
  --generate \
  --prompts ./knowledge-base/prompts.json \
  --out-root ./out \
  --db ./database \
  --outs ./out \
  --out-csv ./out/metrics.csv \
  --models "ollama/llama3.2:1b,ollama/qwen2:0.5b"

# 2) Judge
python3 eval_judge.py \
  --db ./database \
  --outs ./out \
  --refusals ./refusal_patterns.json \
  --prompts ./knowledge-base/prompts.json \
  --correct-threshold 0.30 \
  --out-csv ./out/metrics_judged.csv \
  --summary ./out/summary_by_model.tsv

# 3) Visualize (+ by-mode)
python3 visualize_judgement.py \
  --csv ./out/metrics_judged.csv \
  --out-dir ./out/vis \
  --save-by-mode ./out/vis/judgement_by_mode.png
