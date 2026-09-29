#!/usr/bin/env bash
# UserPromptSubmit hook: append every user prompt to docs/dev-prompts.txt.
# Append-only — never rewrites existing content.
set -euo pipefail

input="$(cat)"
project_dir="${CLAUDE_PROJECT_DIR:-$(printf "%s" "$input" | jq -r '.cwd')}"
log_file="$project_dir/docs/dev-prompts.txt"

prompt="$(printf "%s" "$input" | jq -r '.prompt // ""')"
transcript="$(printf "%s" "$input" | jq -r '.transcript_path // ""')"

# Model: prefer hook payload, then the most recent assistant message in the transcript,
# then the configured model, then a default.
model="$(printf "%s" "$input" | jq -r '.model // empty | if type == "object" then (.id // .display_name // empty) else . end')"
if [[ -z "$model" && -n "$transcript" && -f "$transcript" ]]; then
  model="$(tail -n 500 "$transcript" | jq -r 'select(.type == "assistant") | .message.model // empty' 2>/dev/null | grep -v '^<synthetic>$' | tail -n 1 || true)"
fi
if [[ -z "$model" ]]; then
  model="$(jq -r '.model // empty' "$project_dir/.claude/settings.json" "$HOME/.claude/settings.json" 2>/dev/null | head -n 1 || true)"
fi
model="${model:-claude-opus-5-5}"

timestamp="$(TZ='Asia/Singapore' date '+%Y-%m-%d %H:%M:%S')"

mkdir -p "$(dirname "$log_file")"
# Ensure we start on a fresh line if the file doesn't end with a newline.
if [[ -s "$log_file" && -n "$(tail -c 1 "$log_file")" ]]; then
  printf '\n' >> "$log_file"
fi

{
  printf '\n'
  printf 'Date & Time (GMT+8): %s\n' "$timestamp"
  printf 'AI Model Used: %s\n' "$model"
  printf 'Original Prompt:\n'
  printf '%s\n' "$prompt"
} >> "$log_file"
