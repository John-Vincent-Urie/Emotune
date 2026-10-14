#!/usr/bin/env bash
# Queued Taglish pipeline: wait for the running retrain, then
#   1. snapshot its fresh Text-Emotion stage-1 checkpoint,
#   2. MLM-adapt that encoder on FiReCS text (adapt_taglish_mlm.py),
#   3. run the EmoTune final stage from it into a *separate* output dir,
# so the result can be compared with the retrain before anything is promoted.
#
# Usage: ml_model/run_taglish_pipeline.sh [pid-to-wait-for]
set -euo pipefail
cd "$(dirname "$0")/.."

WAIT_PID="${1:-}"
RETRAIN_LOG=ml_model/artifacts/train_bert_text_emotion_retrain.log
MODELS=backend/ml/models
STAGE1_SNAPSHOT=$MODELS/stage1_textemotion_retrain.fallback

if [[ -n "$WAIT_PID" ]]; then
  echo "[$(date)] waiting for PID $WAIT_PID to exit"
  while kill -0 "$WAIT_PID" 2>/dev/null; do sleep 60; done
  echo "[$(date)] PID $WAIT_PID exited"
fi

if ! grep -q "Training complete!" "$RETRAIN_LOG"; then
  echo "Retrain did not finish cleanly (no 'Training complete!' in $RETRAIN_LOG); not continuing."
  exit 1
fi

# The stage checkpoint has no tokenizer files (the Trainer is not given one);
# the final model dir does, and it is the same bert-base-uncased tokenizer.
CKPT=$(ls -d $MODELS/bert_emotion_model/stage_1_text_emotion_150k/checkpoint-* | sort -t- -k2 -n | tail -1)
echo "[$(date)] snapshotting $CKPT -> $STAGE1_SNAPSHOT"
rm -rf "$STAGE1_SNAPSHOT"
cp -r "$CKPT" "$STAGE1_SNAPSHOT"
cp $MODELS/bert_emotion_model/{vocab.txt,tokenizer.json,tokenizer_config.json,special_tokens_map.json} "$STAGE1_SNAPSHOT"/

echo "[$(date)] step 2: FiReCS MLM adaptation"
HF_HUB_OFFLINE=1 TAGLISH_MLM_SOURCE="$STAGE1_SNAPSHOT" \
  python3 ml_model/adapt_taglish_mlm.py > ml_model/artifacts/adapt_taglish_mlm.log 2>&1

echo "[$(date)] step 3: EmoTune final stage from the adapted encoder"
HF_HUB_OFFLINE=1 \
EMOTUNE_MODEL_NAME="$PWD/$MODELS/stage1_taglish_mlm" \
EMOTUNE_OUTPUT_DIR="$PWD/$MODELS/bert_emotion_model_taglish" \
EMOTUNE_ENABLE_GOEMOTIONS=false \
EMOTUNE_ENABLE_DAIR_EMOTION=false \
EMOTUNE_ENABLE_TEXT_EMOTION=false \
EMOTUNE_ENABLE_CUSTOM_FINAL_STAGE=true \
EMOTUNE_DATASET_PATH=dataset/emotune_combined.csv \
EMOTUNE_CUSTOM_REPEAT_FACTOR=3 \
EMOTUNE_NUM_EPOCHS=4 \
  python3 ml_model/train_bert.py > ml_model/artifacts/train_bert_taglish.log 2>&1

echo "[$(date)] done"
grep -E "EmoTune (Test Accuracy|Weighted F1)" "$RETRAIN_LOG" | sed 's/^/retrain: /'
grep -E "EmoTune (Test Accuracy|Weighted F1)" ml_model/artifacts/train_bert_taglish.log | sed 's/^/taglish: /'
