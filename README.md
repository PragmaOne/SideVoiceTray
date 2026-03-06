# SideVoiceTray

Local speech-to-text tray app for Windows.

## What it does

- Runs in system tray.
- Starts/stops recording by pressing a bound mouse button, a bound 2-key keyboard combo, or both at the same time.
- Shows always-on-top on-screen status while recording and processing.
- Converts speech to text locally (Whisper via `faster-whisper`).
- Uses local Whisper output directly and types it into the active window.

## Requirements

- Windows 10/11
- Python 3.10+
- NVIDIA GPU is recommended for the default `cuda + float16` profile.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure

1. `config.json` is auto-created on first run.
2. Optional: copy `config.example.json` to `config.json` and edit:
   - `stt.model`: `large-v3` by default for maximum Russian STT quality.
   - `stt.model_path`: optional local path to a bundled faster-whisper model folder.
   - `stt.auto_download_model`: when enabled, the app downloads the configured model into its local `models` folder if it is missing.
   - `stt.model_download_dir`: local folder for bundled or auto-downloaded models.
   - `stt.device`: `cuda` by default for fastest processing on modern NVIDIA GPUs. If CUDA is unavailable, the app falls back to CPU automatically.
   - `stt.compute_type`: `float16` by default for the best speed/quality balance on NVIDIA GPUs.
   - `stt.whisper_rescue_enabled`: second sensitive pass for quiet/mumbled speech.
   - `stt.rescue_min_duration_seconds`: allows rescue pass to kick in even on shorter phrases.
   - `stt.audio_boost_enabled`: aggressive boost for quiet mic input (enabled in the high-accuracy profile).
   - `stt.min_input_rms`: silence gate to prevent random hallucinations on pure silence.
   - `stt.sensitive_temperature`: temperature fallback ladder used only on rescue pass for hard-to-hear phrases.
   - `stt.hallucination_silence_threshold`: trims silence-driven hallucinations more aggressively.
   - `stt.mixed_language_fallback`: adds a mixed-language Whisper pass to better preserve English words inside Russian speech.
   - `stt.prefix_recovery_enabled`: adds a no-VAD recovery pass for short phrases so words like `ну` / `но` are less likely to be clipped at the start.
   - `stt.initial_prompt`: bias prompt for your speech domain; default profile now explicitly preserves anglicisms and short leading words.
   - `stt.hotwords`: add your common English terms, names, slang, or profanity to improve detection.
   - `stt.language`: keep `ru` for strict Russian recognition.
   - `hotkey.mode`: `mouse`, `keyboard`, or `both`.
   - `hotkey.mouse_button`: mouse trigger when mouse hotkey is enabled.
   - `hotkey.keyboard_combo`: two keys for keyboard hotkey mode (example: `["ctrl", "space"]`).
   - `hotkey.keyboard_combo_timeout_seconds`: how long the app waits between the two keys in keyboard mode (set around `3.0-4.0` if you press slowly).

## Run

```bash
python run.py
```

or:

```bash
start.bat
```

Hidden tray launch without console:

```bash
start_hidden.vbs
```

Build one-file `.exe` without console:

```bash
build_exe.bat
```

If `dist\SideVoiceTray.exe` is currently running from the tray, close it first before rebuilding.

Prepare an offline release with bundled Whisper model:

```bash
prepare_offline_release.bat
```

Build an installer package:

```bash
build_installer.bat
```

Install the current local release into `%LocalAppData%\Programs\SideVoiceTray`:

```bash
install_release.bat
```

## Tray controls

- `Settings`: open a small desktop window to edit active hotkeys, keyboard timeout, typed-text spacing, indicator labels, `initial_prompt`, and `hotwords` without hand-editing `config.json`.
- `Pause/Resume`: temporarily disable/enable all active hotkeys.
- `Bind Mouse Hotkey (next mouse click)`: click this item, then press the mouse button you want to use as trigger.
- `Bind Keyboard Hotkey (next 2 keys)`: click this item, then press the two keys you want to use together.
- `Exit`: quit the app.

## Notes

- First Whisper model load can take time.
- `large-v3` gives highest accuracy, but is heavier and slower than smaller Whisper models.
- Default runtime is tuned for NVIDIA GPU acceleration: `device=cuda`, `compute_type=float16`.
- If CUDA load fails, the app automatically retries on CPU so startup still succeeds.
- `start.bat` now launches the source app through `python.exe`, so startup errors stay visible in the console.
- `start_hidden.vbs` starts the tray app fully hidden from the beginning.
- Source launch now brings up the tray immediately and loads Whisper in the background, instead of blocking startup on model initialization.
- `build_exe.bat` builds `dist\SideVoiceTray.exe` as a one-file Windows GUI app without a console window.
- `prepare_offline_release.bat` builds the exe and downloads the Whisper model into `dist\models`, so the app can run offline on another Windows machine.
- `build_installer.bat` prepares an offline release and then builds an Inno Setup installer if Inno Setup 6 is installed.
- If Inno Setup is missing, `build_installer.bat` now installs a local copy automatically and uses it to build the installer.
- `install_release.bat` installs the latest built release into your local Programs folder and creates Start Menu/Desktop shortcuts without requiring Inno Setup.
- If no local model is bundled, the app can auto-download the configured Whisper model into its local `models` folder on first launch.
- Quiet/unclear speech is handled by an extra low-confidence retry pass that now evaluates both the original audio and a boosted variant.
- Short leading words and mixed Russian/English phrases get extra recovery passes before final candidate selection.
- Common silence hallucinations such as subtitle/credits-like phrases are filtered out before final output.
- Final output comes directly from local Whisper with light normalization only.
- Russian mode is locked to Russian orthography (prevents accidental Ukrainian letters and translit output).
- Choosing `Exit` from the tray closes the app process instead of leaving a background console open.
- Typing works into currently focused input field in any app.
