# SideVoiceTray

Local speech-to-text tray app for Windows.

## What it does

- Runs in system tray.
- Starts/stops recording by pressing side mouse button (`X1`) once.
- Shows always-on-top on-screen status while recording and processing.
- Converts speech to text locally (Whisper via `faster-whisper`).
- Sends raw text to LM Studio local model for punctuation and spelling cleanup.
- Types final text into active window like keyboard input.

## Requirements

- Windows 10/11
- Python 3.10+
- LM Studio running local server (`http://127.0.0.1:1234`)
- Loaded chat model in LM Studio for formatting (your GGUF model)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure

1. `config.json` is auto-created on first run.
2. Optional: copy `config.example.json` to `config.json` and edit:
   - `lm_studio.model`: set your exact loaded model id from LM Studio.
   - `lm_studio.max_output_tokens`: allow long clean outputs for big dictations.
   - `lm_studio.repair_retries`: automatic retry if model outputs meta/instruction text.
   - `lm_studio.quality_second_pass`: second LLM verification pass for cleaner final text.
   - `lm_studio.quality_refine_passes`: number of verification/refine iterations (higher = better quality, slower).
   - `stt.model`: `large-v3` by default for maximum Russian STT quality.
   - `stt.whisper_rescue_enabled`: second sensitive pass for quiet/mumbled speech.
   - `stt.audio_boost_enabled`: optional aggressive boost for very quiet mic input (off by default).
   - `stt.min_input_rms`: silence gate to prevent random hallucinations on pure silence.
   - `stt.hotwords`: add your common English terms, names, slang, or profanity to improve detection.
   - `stt.language`: keep `ru` for strict Russian recognition.
   - `output.target_language`: `none` / `en` / `es` / `pl` / `zh`.
   - `hotkey.mouse_button`: `x1` (default) or `x2`.

## Run

```bash
python run.py
```

or:

```bash
start.bat
```

## Tray controls

- `Pause/Resume`: temporarily disable/enable mouse hotkey.
- Output language switch: `Russian (No translation)` / `English` / `Spanish` / `Polish` / `Chinese (Simplified)`.
- `Bind Hotkey (next mouse click)`: click this item, then press the mouse button you want to use as trigger.
- `Exit`: quit the app.

## Notes

- First Whisper model load can take time.
- `large-v3` gives highest accuracy, but is heavier and slower.
- Quiet/unclear speech is handled by an extra low-confidence retry pass (stable profile).
- LLM formatter has auto-repair and optional second verification pass to prevent meta replies.
- High-quality mode can run multiple LLM refine passes when your local model is fast.
- If LLM tries to answer like an assistant, output is rejected by overlap-based guard and falls back safely.
- The formatter preserves profanity and keeps spoken English terms in Latin script.
- Russian mode is locked to Russian orthography (prevents accidental Ukrainian letters and translit output).
- If LM Studio is unavailable, app falls back to raw STT text.
- Typing works into currently focused input field in any app.
