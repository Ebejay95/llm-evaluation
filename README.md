# LLM-Evaluation by Aleph Alpha
## Judge-Evaluation (Lyrics)

### Pipeline
1. **Generate** (optional): Modelle produzieren Antworten pro Prompt → `./resources/out/<model_dir>/*.txt`
2. **Judge**: `eval_judge.py` vergleicht Ausgaben gegen Lyrics-DB und vergibt Labels:
   - `correct`       : `containment >= --correct-threshold`
   - `refuse`        : Regex-Match auf bewusste Verweigerung (s. `refusal_patterns.json`)
   - `hallucinate`   : sonst (niedrige Coverage, kein Refuse)
   - `error`         : Lese-/Verarbeitungsfehler
3. **Visualize**: `visualize_judgement.py` zeigt pro Modell Stacked Bars (Grün/Gelb/Orange/Rot).

### Commands
```bash
# 1) (optional) Generate mit deinem bestehenden Generator
python3 resources/eval_coverage.py \
  --generate \
  --models "ollama/llama3.2:1b,ollama/qwen2:0.5b" \
  --prompts ./resources/knowledge-base/prompts.json \
  --out-root ./resources/out \
  --db ./resources/database \
  --outs ./resources/out \
  --out-csv ./resources/out/metrics.csv

# 2) Judge
python3 resources/eval_judge.py \
  --db ./resources/database \
  --outs ./resources/out \
  --refusals ./resources/refusal_patterns.json \
  --correct-threshold 0.30 \
  --out-csv ./resources/out/metrics_judged.csv \
  --summary ./resources/out/summary_by_model.tsv

# 3) Visualize
python3 resources/visualize_judgement.py \
  --csv ./resources/out/metrics_judged.csv
