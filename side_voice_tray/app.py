from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pystray
import sounddevice as sd
import tkinter as tk
from faster_whisper import WhisperModel
from faster_whisper.utils import download_model
from PIL import Image, ImageDraw
from pynput import keyboard, mouse

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_DLL_DIR_HANDLES: list[Any] = []
_REGISTERED_DLL_DIRS: set[str] = set()
_SINGLE_INSTANCE_MUTEX: Any = None


DEFAULT_CONFIG: dict[str, Any] = {
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
    },
    "stt": {
        "model": "large-v3",
        "model_path": None,
        "auto_download_model": True,
        "model_download_dir": "models",
        "device": "cuda",
        "compute_type": "float16",
        "language": "ru",
        "beam_size": 18,
        "best_of": 18,
        "patience": 1.8,
        "temperature": 0.0,
        "repetition_penalty": 1.0,
        "condition_on_previous_text": True,
        "prompt_reset_on_temperature": 0.5,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.34,
        "hallucination_silence_threshold": 0.3,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": 0.36,
            "min_speech_duration_ms": 80,
            "min_silence_duration_ms": 420,
            "speech_pad_ms": 320,
        },
        "mixed_language_fallback": True,
        "language_detection_threshold": 0.4,
        "language_detection_segments": 5,
        "whisper_rescue_enabled": True,
        "rescue_min_duration_seconds": 0.55,
        "low_confidence_avg_logprob": -0.9,
        "low_confidence_no_speech_prob": 0.58,
        "audio_boost_enabled": True,
        "target_rms": 0.12,
        "max_gain_db": 34.0,
        "min_input_rms": 0.00035,
        "retry_without_vad": True,
        "prefix_recovery_enabled": True,
        "prefix_recovery_max_duration_seconds": 4.8,
        "sensitive_beam_size": 24,
        "sensitive_best_of": 24,
        "sensitive_patience": 3.0,
        "sensitive_temperature": [0.0, 0.2, 0.4, 0.6],
        "sensitive_prompt_reset_on_temperature": 0.35,
        "sensitive_no_speech_threshold": 0.18,
        "sensitive_log_prob_threshold": -1.55,
        "initial_prompt": (
            "Русская разговорная речь с англицизмами, английскими брендами, "
            "техническими терминами и сленгом. "
            "Сохраняй английские слова, аббревиатуры, названия продуктов, игр, "
            "библиотек и технологий в исходной форме на латинице, если они "
            "произнесены по-английски. "
            "Не удаляй короткие начальные слова в начале фразы: ну, но, да, а, вот. "
            "Не придумывай текст на тишине и не дописывай фразы, которых не было в речи."
        ),
        "hotwords": [
            "Python",
            "Docker",
            "GitHub",
            "API",
            "SQL",
            "JavaScript",
            "TypeScript",
            "Windows",
            "Linux",
            "Chrome",
            "Google",
            "Discord",
            "Steam",
            "OBS",
            "NVIDIA",
            "CUDA",
            "GPU",
            "CPU",
            "FPS",
            "DirectX",
            "OpenGL",
            "Unreal",
            "Unity",
            "Telegram",
            "YouTube",
            "Twitch",
            "OpenAI",
            "блять",
            "блядь",
            "сука",
            "нахуй",
            "пиздец",
            "хуй",
            "ебать",
            "ебаный",
        ],
    },
    "hotkey": {
        "mode": "both",
        "mouse_button": "x1",
        "keyboard_combo": ["ctrl", "space"],
        "keyboard_combo_timeout_seconds": 4.0,
    },
    "typing": {
        "append_space": True,
    },
    "ui": {
        "recording_text": "REC",
        "processing_text": "PROCESSING",
    },
}

MOUSE_BUTTON_BY_NAME: dict[str, mouse.Button] = {
    "left": mouse.Button.left,
    "right": mouse.Button.right,
    "middle": mouse.Button.middle,
    "x1": mouse.Button.x1,
    "x2": mouse.Button.x2,
}
MOUSE_NAME_BY_BUTTON: dict[mouse.Button, str] = {
    button: name for name, button in MOUSE_BUTTON_BY_NAME.items()
}
HOTKEY_MODES = {"mouse", "keyboard", "both"}
UKRAINIAN_TO_RUSSIAN_TRANSLATION_TABLE = str.maketrans(
    {
        "і": "и",
        "І": "И",
        "ї": "и",
        "Ї": "И",
        "є": "е",
        "Є": "Е",
        "ґ": "г",
        "Ґ": "Г",
    }
)
SPOKEN_SYMBOL_NORMALIZATION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bплюс\b", re.IGNORECASE), "+"),
)

KEY_NAME_NORMALIZATION_MAP: dict[str, str] = {
    "control": "ctrl",
    "control_l": "ctrl",
    "control_r": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "option_l": "alt",
    "option_r": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "cmd": "meta",
    "cmd_l": "meta",
    "cmd_r": "meta",
    "caps_lock": "capslock",
    "page_up": "pageup",
    "page_down": "pagedown",
    "prtsc": "printscreen",
    "prt_sc": "printscreen",
    "print_screen": "printscreen",
    "printscreen": "printscreen",
    "scrlk": "scrolllock",
    "scr_lk": "scrolllock",
    "scroll_lock": "scrolllock",
    "scrolllock": "scrolllock",
}
KEY_LABEL_MAP: dict[str, str] = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "meta": "Meta",
    "space": "Space",
    "enter": "Enter",
    "tab": "Tab",
    "esc": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "capslock": "CapsLock",
    "pause": "Pause",
    "numlock": "NumLock",
    "menu": "Menu",
    "printscreen": "PrintScreen",
    "scrolllock": "ScrollLock",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}
VK_KEY_NAME_MAP: dict[int, str] = {
    8: "backspace",
    9: "tab",
    13: "enter",
    160: "shift",
    161: "shift",
    162: "ctrl",
    163: "ctrl",
    164: "alt",
    165: "alt",
    16: "shift",
    17: "ctrl",
    18: "alt",
    19: "pause",
    20: "capslock",
    27: "esc",
    32: "space",
    186: ";",
    187: "=",
    188: ",",
    189: "-",
    190: ".",
    191: "/",
    192: "`",
    33: "pageup",
    34: "pagedown",
    35: "end",
    36: "home",
    37: "left",
    38: "up",
    39: "right",
    40: "down",
    44: "printscreen",
    45: "insert",
    46: "delete",
    219: "[",
    220: "\\",
    221: "]",
    222: "'",
    91: "meta",
    92: "meta",
    93: "menu",
    144: "numlock",
    145: "scrolllock",
}
MODIFIER_KEY_NAMES = {"ctrl", "alt", "shift", "meta"}
NOISY_BIND_KEY_NAMES = {"delete"}
LEADING_SPEECH_PARTICLES = {
    "ну",
    "но",
    "да",
    "а",
    "вот",
    "так",
}
KNOWN_HALLUCINATION_PATTERNS = (
    re.compile(r"\bсубтит(?:ры|р)\b.*\b(?:созда\w+|сгенерир\w+|делал|by)\b", re.IGNORECASE),
    re.compile(r"\b(?:subtitles?|captions?)\b.*\b(?:by|generated|created)\b", re.IGNORECASE),
    re.compile(r"\bспасибо за просмотр\b", re.IGNORECASE),
    re.compile(r"\bthanks for watching\b", re.IGNORECASE),
    re.compile(r"\bподписывай(?:тесь|ся) на канал\b", re.IGNORECASE),
    re.compile(r"\bsubscribe to (?:the )?channel\b", re.IGNORECASE),
)


def get_app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundle_runtime_dir() -> Path | None:
    runtime_dir = getattr(sys, "_MEIPASS", None)
    if not runtime_dir:
        return None
    return Path(runtime_dir)


def acquire_single_instance_mutex() -> bool:
    global _SINGLE_INSTANCE_MUTEX

    if os.name != "nt":
        return True

    mutex_name = "Local\\SideVoiceTray.Singleton"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ctypes.set_last_error(0)
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        return True

    _SINGLE_INSTANCE_MUTEX = mutex
    already_exists_error = 183
    return ctypes.get_last_error() != already_exists_error


def configure_windows_cuda_runtime() -> None:
    if os.name != "nt":
        return

    base_dir = get_app_base_dir()
    bundle_runtime_dir = get_bundle_runtime_dir()
    candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        base_dir / ".venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        base_dir / "nvidia" / "cublas" / "bin",
    ]
    if bundle_runtime_dir is not None:
        candidates.extend(
            [
                bundle_runtime_dir / "nvidia" / "cublas" / "bin",
                bundle_runtime_dir,
            ]
        )

    path_var = os.environ.get("PATH", "")
    path_lower = path_var.lower()

    for candidate in candidates:
        if not candidate.exists():
            continue

        candidate_str = str(candidate)
        candidate_norm = candidate_str.lower()
        if candidate_norm in _REGISTERED_DLL_DIRS:
            continue

        if candidate_norm not in path_lower:
            os.environ["PATH"] = candidate_str + os.pathsep + path_var
            path_var = os.environ["PATH"]
            path_lower = path_var.lower()

        if hasattr(os, "add_dll_directory"):
            try:
                handle = os.add_dll_directory(candidate_str)
                _DLL_DIR_HANDLES.append(handle)
            except Exception as exc:
                print(f"[stt] unable to register CUDA DLL directory: {exc}")

        _REGISTERED_DLL_DIRS.add(candidate_norm)


def deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG

    with config_path.open("r", encoding="utf-8") as handle:
        user_config = json.load(handle)

    return deep_merge(DEFAULT_CONFIG, user_config)


def normalize_keyboard_key_name(key: keyboard.Key | keyboard.KeyCode | Any) -> str | None:
    if isinstance(key, keyboard.KeyCode):
        vk = getattr(key, "vk", None)
        if isinstance(vk, int):
            mapped = VK_KEY_NAME_MAP.get(vk)
            if mapped is not None:
                return mapped
            if 65 <= vk <= 90:
                return chr(vk).lower()
            if 48 <= vk <= 57:
                return chr(vk)
            if 96 <= vk <= 105:
                return f"num{vk - 96}"
            if 112 <= vk <= 123:
                return f"f{vk - 111}"
        if key.char:
            char = str(key.char).strip()
            if char:
                return char.lower()
        if isinstance(vk, int) and 96 <= vk <= 105:
            return f"num{vk - 96}"
        return None

    if isinstance(key, keyboard.Key):
        name = str(getattr(key, "name", "") or "").strip().lower()
        if not name:
            return None
        return KEY_NAME_NORMALIZATION_MAP.get(name, name)

    return None


def hotkey_part_label(name: str) -> str:
    normalized = str(name).strip().lower()
    if not normalized:
        return "?"
    if normalized in KEY_LABEL_MAP:
        return KEY_LABEL_MAP[normalized]
    if len(normalized) == 1:
        return normalized.upper()
    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized.upper()
    if normalized.startswith("num") and normalized[3:].isdigit():
        return f"Num{normalized[3:]}"
    return normalized.replace("_", " ").title()


def normalize_whisper_output(text: str) -> str:
    cleaned = str(text).strip()
    if not cleaned:
        return ""
    normalized = cleaned.translate(UKRAINIAN_TO_RUSSIAN_TRANSLATION_TABLE)
    for pattern, replacement in SPOKEN_SYMBOL_NORMALIZATION_RULES:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def tokenize_word_list(text: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())


def latin_word_set(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9+._-]*", text)}


def leading_particle_prefix_len(longer_text: str, shorter_text: str) -> int:
    longer_tokens = tokenize_word_list(longer_text)
    shorter_tokens = tokenize_word_list(shorter_text)
    if not longer_tokens or not shorter_tokens or len(longer_tokens) <= len(shorter_tokens):
        return 0

    prefix_len = len(longer_tokens) - len(shorter_tokens)
    if prefix_len < 1 or prefix_len > 2:
        return 0
    if longer_tokens[prefix_len:] != shorter_tokens:
        return 0
    if all(token in LEADING_SPEECH_PARTICLES for token in longer_tokens[:prefix_len]):
        return prefix_len
    return 0


class RecordingIndicator:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.92)
        self.window.configure(bg="#111111")

        self.label = tk.Label(
            self.window,
            text="REC",
            fg="#ff4d4f",
            bg="#111111",
            font=("Segoe UI", 14, "bold"),
            padx=14,
            pady=8,
        )
        self.label.pack()
        self.window.withdraw()

        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.root.after(40, self._drain_queue)

    def _position_window(self) -> None:
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        x = self.window.winfo_screenwidth() - width - 24
        y = 24
        self.window.geometry(f"+{x}+{y}")

    def _drain_queue(self) -> None:
        while True:
            try:
                action, payload = self._queue.get_nowait()
            except queue.Empty:
                break

            if action == "show":
                self.label.configure(text=payload)
                self._position_window()
                self.window.deiconify()
            elif action == "hide":
                self.window.withdraw()
            elif action == "quit":
                self.root.quit()
                return

        self.root.after(40, self._drain_queue)

    def show(self, text: str) -> None:
        self._queue.put(("show", text))

    def hide(self) -> None:
        self._queue.put(("hide", ""))

    def stop(self) -> None:
        self._queue.put(("quit", ""))

    def run(self) -> None:
        self.root.mainloop()


class AudioRecorder:
    def __init__(self, sample_rate: int, channels: int) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._recording = False

    def _callback(self, indata: np.ndarray, _frames: int, _time: Any, status: sd.CallbackFlags) -> None:
        if status:
            print(f"[audio] status: {status}")

        with self._lock:
            if self._recording:
                self._frames.append(indata.copy())

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                callback=self._callback,
            )
            self._stream.start()

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._recording:
                return np.array([], dtype=np.float32)
            self._recording = False
            stream = self._stream
            self._stream = None

        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            frames = self._frames
            self._frames = []

        if not frames:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(frames, axis=0)
        if audio.ndim > 1:
            audio = np.squeeze(audio, axis=1)

        return audio.astype(np.float32)


@dataclass
class TranscriptionCandidate:
    text: str
    avg_logprob: float
    no_speech_prob: float
    source: str
    language: str | None
    detected_language: str | None
    language_probability: float


class WhisperTranscriber:
    def __init__(self, config: dict[str, Any], sample_rate: int) -> None:
        configure_windows_cuda_runtime()

        self.model_name = str(config["model"])
        self.model_path = self._normalize_optional_text(config.get("model_path"))
        self.auto_download_model = bool(config.get("auto_download_model", True))
        self.model_download_dir = self._normalize_optional_text(config.get("model_download_dir")) or "models"
        self.sample_rate = sample_rate
        self.language = self._normalize_language(config.get("language"))
        self.beam_size = int(config["beam_size"])
        self.best_of = int(config.get("best_of", self.beam_size))
        self.patience = float(config.get("patience", 1.0))
        self.decode_temperature = self._normalize_temperature(config.get("temperature", 0.0), fallback=0.0)
        self.repetition_penalty = float(config.get("repetition_penalty", 1.0))
        self.condition_on_previous_text = bool(config.get("condition_on_previous_text", True))
        self.prompt_reset_on_temperature = float(config.get("prompt_reset_on_temperature", 0.5))
        self.compression_ratio_threshold = float(config.get("compression_ratio_threshold", 2.4))
        self.log_prob_threshold = float(config.get("log_prob_threshold", -1.0))
        self.no_speech_threshold = float(config.get("no_speech_threshold", 0.45))
        self.hallucination_silence_threshold = self._normalize_optional_float(
            config.get("hallucination_silence_threshold", None)
        )
        self.vad_filter = bool(config["vad_filter"])
        self.vad_parameters = config.get("vad_parameters")
        self.mixed_language_fallback = bool(config.get("mixed_language_fallback", True))
        self.language_detection_threshold = float(config.get("language_detection_threshold", 0.4))
        self.language_detection_segments = int(config.get("language_detection_segments", 3))
        self.whisper_rescue_enabled = bool(config.get("whisper_rescue_enabled", True))
        self.rescue_min_duration_seconds = float(config.get("rescue_min_duration_seconds", 0.8))
        self.low_confidence_avg_logprob = float(config.get("low_confidence_avg_logprob", -1.05))
        self.low_confidence_no_speech_prob = float(config.get("low_confidence_no_speech_prob", 0.72))
        self.audio_boost_enabled = bool(config.get("audio_boost_enabled", True))
        self.target_rms = float(config.get("target_rms", 0.09))
        self.max_gain_db = float(config.get("max_gain_db", 28.0))
        self.max_linear_gain = float(10.0 ** (self.max_gain_db / 20.0))
        self.min_input_rms = float(config.get("min_input_rms", 0.0012))
        self.retry_without_vad = bool(config.get("retry_without_vad", True))
        self.prefix_recovery_enabled = bool(config.get("prefix_recovery_enabled", True))
        self.prefix_recovery_max_duration_seconds = float(config.get("prefix_recovery_max_duration_seconds", 4.8))
        self.sensitive_beam_size = int(config.get("sensitive_beam_size", max(self.beam_size, 12)))
        self.sensitive_best_of = int(config.get("sensitive_best_of", max(self.best_of, 12)))
        self.sensitive_patience = float(config.get("sensitive_patience", max(self.patience, 1.8)))
        self.sensitive_decode_temperature = self._normalize_temperature(
            config.get("sensitive_temperature", self.decode_temperature),
            fallback=self.decode_temperature,
        )
        self.sensitive_prompt_reset_on_temperature = float(
            config.get("sensitive_prompt_reset_on_temperature", self.prompt_reset_on_temperature)
        )
        self.sensitive_no_speech_threshold = float(
            config.get("sensitive_no_speech_threshold", min(self.no_speech_threshold, 0.2))
        )
        self.sensitive_log_prob_threshold = float(
            config.get("sensitive_log_prob_threshold", min(self.log_prob_threshold, -1.45))
        )
        self.initial_prompt = self._normalize_optional_text(config.get("initial_prompt"))
        self.hotwords = self._normalize_hotwords(config.get("hotwords"))
        self.compute_type = str(config["compute_type"])
        self.device = str(config["device"])
        self.model_reference = self._resolve_model_reference()

        print(f"[stt] loading Whisper model from {self.model_reference}...")
        self.model = self._load_model_with_compute_fallback()
        print(f"[stt] Whisper model ready (device={self.device}, compute_type={self.compute_type})")

    def _resolve_model_reference(self) -> str:
        explicit_model_path = self._resolve_model_path_from_config()
        if explicit_model_path is not None:
            print(f"[stt] using configured local model path: {explicit_model_path}")
            return str(explicit_model_path)

        bundled_model_path = self._resolve_packaged_model_path()
        if bundled_model_path is not None:
            print(f"[stt] using packaged local model: {bundled_model_path}")
            return str(bundled_model_path)

        if not self.auto_download_model:
            return self.model_name

        target_root = get_app_base_dir() / self.model_download_dir
        target_root.mkdir(parents=True, exist_ok=True)
        print(f"[stt] local model not found, downloading {self.model_name} to {target_root}...")
        downloaded_path = download_model(
            self.model_name,
            output_dir=str(target_root),
            cache_dir=str(target_root),
            local_files_only=False,
        )
        print(f"[stt] model downloaded to {downloaded_path}")
        return str(Path(downloaded_path))

    def _resolve_model_path_from_config(self) -> Path | None:
        if not self.model_path:
            return None

        candidate = Path(self.model_path)
        if not candidate.is_absolute():
            candidate = get_app_base_dir() / candidate
        candidate = candidate.resolve()
        if self._looks_like_whisper_model_dir(candidate):
            return candidate

        print(f"[stt] configured model_path not found or incomplete: {candidate}")
        return None

    def _resolve_packaged_model_path(self) -> Path | None:
        candidates: list[Path] = []
        base_dir = get_app_base_dir()
        candidates.append(base_dir / self.model_download_dir)
        candidates.append(base_dir / self.model_download_dir / self.model_name)

        bundle_runtime_dir = get_bundle_runtime_dir()
        if bundle_runtime_dir is not None:
            candidates.append(bundle_runtime_dir / self.model_download_dir)
            candidates.append(bundle_runtime_dir / self.model_download_dir / self.model_name)

        for candidate in candidates:
            if self._looks_like_whisper_model_dir(candidate):
                return candidate.resolve()
        return None

    @staticmethod
    def _looks_like_whisper_model_dir(path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        has_weights = (path / "model.bin").exists()
        has_metadata = (path / "config.json").exists() or (path / "tokenizer.json").exists()
        return has_weights and has_metadata

    def _load_model_with_compute_fallback(self) -> WhisperModel:
        last_error: Exception | None = None
        for device, compute_types in self._load_attempts():
            seen: set[str] = set()
            for compute_type in compute_types:
                if compute_type in seen:
                    continue
                seen.add(compute_type)
                try:
                    model = WhisperModel(
                        model_size_or_path=self.model_reference,
                        device=device,
                        compute_type=compute_type,
                    )
                    self.device = device
                    self.compute_type = compute_type
                    return model
                except Exception as exc:
                    last_error = exc
                    print(f"[stt] unable to load Whisper on {device} with {compute_type}, retrying...")

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to load Whisper model")

    def _load_attempts(self) -> list[tuple[str, list[str]]]:
        attempts = [(self.device, self._compute_type_attempts(self.device, self.compute_type))]
        if self.device != "cpu":
            attempts.append(("cpu", self._compute_type_attempts("cpu", "float32")))
        return attempts

    @staticmethod
    def _compute_type_attempts(device: str, preferred: str) -> list[str]:
        attempts = [preferred]
        if device == "cuda":
            if preferred == "float16":
                attempts.extend(["int8_float16", "int8"])
            elif preferred == "int8_float16":
                attempts.append("int8")
            elif preferred == "auto":
                attempts.extend(["float16", "int8_float16", "int8"])
            elif preferred == "float32":
                attempts.extend(["float16", "int8_float16", "int8"])
            else:
                attempts.extend(["float16", "int8_float16", "int8"])
        else:
            if preferred == "float32":
                attempts.append("int8")
            elif preferred == "auto":
                attempts.extend(["float32", "int8"])
            else:
                attempts.extend(["float32", "int8"])
        return attempts

    @staticmethod
    def _is_cuda_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "cublas64_12.dll" in message or "cuda" in message

    @staticmethod
    def _normalize_language(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized or normalized == "auto":
            return None
        return normalized

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)

    @staticmethod
    def _normalize_hotwords(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            words = [str(item).strip() for item in value if str(item).strip()]
            if not words:
                return None
            return ", ".join(words)
        return None

    @staticmethod
    def _normalize_temperature(value: Any, *, fallback: float | tuple[float, ...]) -> float | tuple[float, ...]:
        if isinstance(value, (list, tuple)):
            normalized = tuple(float(item) for item in value)
            if normalized:
                return normalized
            return fallback
        if value is None:
            return fallback
        return float(value)

    def _segments_to_candidate(
        self,
        segments: Any,
        source: str,
        language: str | None,
        detected_language: str | None,
        language_probability: float,
    ) -> TranscriptionCandidate:
        segment_list = list(segments)
        parts: list[str] = []
        avg_logprobs: list[float] = []
        no_speech_probs: list[float] = []
        for segment in segment_list:
            text = segment.text.strip()
            if text:
                parts.append(text)
            avg_logprobs.append(float(getattr(segment, "avg_logprob", -2.0)))
            no_speech_probs.append(float(getattr(segment, "no_speech_prob", 1.0)))

        avg_logprob = sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else -2.0
        no_speech_prob = max(no_speech_probs) if no_speech_probs else 1.0
        return TranscriptionCandidate(
            text=" ".join(parts).strip(),
            avg_logprob=avg_logprob,
            no_speech_prob=no_speech_prob,
            source=source,
            language=language,
            detected_language=detected_language,
            language_probability=language_probability,
        )

    def _build_transcribe_kwargs(
        self,
        language: str | None,
        *,
        sensitive: bool,
        disable_vad: bool,
    ) -> dict[str, Any]:
        beam_size = self.sensitive_beam_size if sensitive else self.beam_size
        best_of = self.sensitive_best_of if sensitive else self.best_of
        patience = self.sensitive_patience if sensitive else self.patience
        temperature = self.sensitive_decode_temperature if sensitive else self.decode_temperature
        prompt_reset_on_temperature = (
            self.sensitive_prompt_reset_on_temperature if sensitive else self.prompt_reset_on_temperature
        )
        no_speech_threshold = self.sensitive_no_speech_threshold if sensitive else self.no_speech_threshold
        log_prob_threshold = self.sensitive_log_prob_threshold if sensitive else self.log_prob_threshold

        kwargs: dict[str, Any] = {
            "language": language,
            "task": "transcribe",
            "beam_size": beam_size,
            "best_of": best_of,
            "patience": patience,
            "temperature": temperature,
            "repetition_penalty": self.repetition_penalty,
            "condition_on_previous_text": self.condition_on_previous_text,
            "prompt_reset_on_temperature": prompt_reset_on_temperature,
            "compression_ratio_threshold": self.compression_ratio_threshold,
            "log_prob_threshold": log_prob_threshold,
            "no_speech_threshold": no_speech_threshold,
            "hallucination_silence_threshold": self.hallucination_silence_threshold,
            "vad_filter": False if disable_vad else self.vad_filter,
            "language_detection_threshold": self.language_detection_threshold,
            "language_detection_segments": self.language_detection_segments,
            "initial_prompt": None if sensitive else self.initial_prompt,
            "hotwords": self.hotwords,
        }
        if self.vad_parameters and not disable_vad:
            kwargs["vad_parameters"] = self.vad_parameters
        return kwargs

    def _transcribe_once(
        self,
        audio: np.ndarray,
        language: str | None,
        *,
        source: str,
        sensitive: bool,
        disable_vad: bool,
    ) -> TranscriptionCandidate:
        segments, info = self.model.transcribe(
            audio,
            **self._build_transcribe_kwargs(language, sensitive=sensitive, disable_vad=disable_vad),
        )
        detected_language = self._normalize_language(getattr(info, "language", None))
        language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        return self._segments_to_candidate(
            segments,
            source=source,
            language=language,
            detected_language=detected_language,
            language_probability=language_probability,
        )

    def _transcribe_with_runtime_fallback(
        self,
        audio: np.ndarray,
        language: str | None,
        *,
        source: str,
        sensitive: bool,
        disable_vad: bool,
    ) -> TranscriptionCandidate:
        try:
            return self._transcribe_once(
                audio,
                language,
                source=source,
                sensitive=sensitive,
                disable_vad=disable_vad,
            )
        except RuntimeError as exc:
            if not self._is_cuda_error(exc):
                raise
            self._switch_to_cpu()
            return self._transcribe_once(
                audio,
                language,
                source=source,
                sensitive=sensitive,
                disable_vad=disable_vad,
            )

    def _switch_to_cpu(self) -> None:
        if self.device == "cpu":
            return

        print("[stt] CUDA runtime unavailable, switching to CPU mode")
        self.device = "cpu"
        for cpu_compute_type in ("float32", "int8"):
            try:
                self.model = WhisperModel(
                    model_size_or_path=self.model_reference,
                    device=self.device,
                    compute_type=cpu_compute_type,
                )
                self.compute_type = cpu_compute_type
                return
            except Exception:
                continue
        raise RuntimeError("Unable to switch Whisper model to CPU")

    def _apply_audio_boost(self, audio: np.ndarray) -> np.ndarray:
        if not self.audio_boost_enabled or audio.size == 0:
            return audio

        boosted = np.array(audio, dtype=np.float32, copy=True)
        boosted -= float(np.mean(boosted))

        # Compression raises quiet parts to make whispered speech easier to decode.
        boosted = np.sign(boosted) * np.sqrt(np.abs(boosted) + 1e-8)

        rms = float(np.sqrt(np.mean(np.square(boosted)) + 1e-9))
        if rms > 0:
            gain = min(self.target_rms / max(rms, 1e-6), self.max_linear_gain)
            boosted *= gain

        peak = float(np.max(np.abs(boosted))) if boosted.size else 0.0
        if peak > 0.98:
            boosted *= 0.98 / peak

        return boosted.astype(np.float32)

    def _candidate_score(self, candidate: TranscriptionCandidate) -> float:
        if not candidate.text:
            return -999.0
        if self._looks_like_prompt_echo(candidate.text):
            return -999.0
        if self._looks_like_known_hallucination(candidate.text):
            return -999.0

        score = candidate.avg_logprob - (0.2 * candidate.no_speech_prob)
        score += min(len(candidate.text), 180) / 1800.0

        detected_language = candidate.detected_language
        detected_prob = max(candidate.language_probability, 0.0)
        if self.language == "ru":
            if detected_language == "ru":
                score += 0.05 * max(detected_prob, 0.3)
            elif detected_language in {"uk", "be"}:
                score -= 0.12 * max(detected_prob, 0.3)

        return score

    def _looks_like_known_hallucination(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        if not normalized:
            return False
        if len(normalized) > 180:
            return False
        if any(pattern.search(normalized) for pattern in KNOWN_HALLUCINATION_PATTERNS):
            return True

        tokens = tokenize_word_list(normalized)
        if len(tokens) >= 6 and len(tokens) % 2 == 0:
            half = len(tokens) // 2
            if tokens[:half] == tokens[half:]:
                return True

        return False

    def _looks_like_prompt_echo(self, text: str) -> bool:
        if not self.initial_prompt:
            return False

        normalized_text = " ".join(text.lower().split())
        normalized_prompt = " ".join(self.initial_prompt.lower().split())
        if not normalized_text or not normalized_prompt:
            return False

        return normalized_text in normalized_prompt or normalized_prompt.startswith(normalized_text)

    def _pick_best_candidate(self, candidates: list[TranscriptionCandidate]) -> TranscriptionCandidate | None:
        non_empty = [candidate for candidate in candidates if candidate.text]
        if not non_empty:
            return None
        return max(non_empty, key=self._candidate_score)

    def _should_retry_low_confidence(
        self,
        best_candidate: TranscriptionCandidate | None,
        duration_seconds: float,
    ) -> bool:
        if not self.whisper_rescue_enabled or duration_seconds < self.rescue_min_duration_seconds:
            return False
        if best_candidate is None:
            return True
        if self._looks_like_known_hallucination(best_candidate.text):
            return True
        if best_candidate.avg_logprob < self.low_confidence_avg_logprob:
            return True
        if best_candidate.no_speech_prob > self.low_confidence_no_speech_prob:
            short_text = len(best_candidate.text) < max(8, int(duration_seconds * 4))
            if short_text:
                return True
        return False

    def _variant_bonus(self, candidate_text: str, all_texts: list[str]) -> float:
        bonus = 0.0
        for other_text in all_texts:
            if other_text == candidate_text:
                continue
            prefix_len = leading_particle_prefix_len(candidate_text, other_text)
            if prefix_len > 0:
                bonus = max(bonus, 0.08 * prefix_len)
        return bonus

    def _build_primary_and_alternative(
        self,
        candidates: list[TranscriptionCandidate],
    ) -> tuple[str, str | None]:
        best_per_text: dict[str, tuple[TranscriptionCandidate, float]] = {}
        for candidate in candidates:
            if not candidate.text:
                continue
            score = self._candidate_score(candidate)
            current = best_per_text.get(candidate.text)
            if current is None or score > current[1]:
                best_per_text[candidate.text] = (candidate, score)

        if not best_per_text:
            return "", None

        all_texts = list(best_per_text.keys())
        ranked = sorted(
            best_per_text.values(),
            key=lambda item: item[1] + self._variant_bonus(item[0].text, all_texts),
            reverse=True,
        )
        primary_text = ranked[0][0].text
        alternative_text = ranked[1][0].text if len(ranked) > 1 else None
        return primary_text, alternative_text

    def _run_prefix_recovery_pass(self, audio: np.ndarray) -> list[TranscriptionCandidate]:
        candidates: list[TranscriptionCandidate] = []

        primary_language = self.language
        language_targets: list[str | None] = [primary_language]
        if self.mixed_language_fallback and primary_language is not None:
            language_targets.append(None)

        for language in language_targets:
            source_language = "mixed" if language is None else "ru"
            source = f"{source_language}-prefix"
            candidate = self._transcribe_with_runtime_fallback(
                audio,
                language,
                source=source,
                sensitive=False,
                disable_vad=True,
            )
            candidates.append(candidate)

        return candidates

    def _run_pass(self, audio: np.ndarray, *, sensitive: bool) -> list[TranscriptionCandidate]:
        disable_vad = sensitive and self.retry_without_vad
        candidates: list[TranscriptionCandidate] = []

        primary_language = self.language
        language_targets: list[str | None] = [primary_language]
        if self.mixed_language_fallback and primary_language is not None:
            language_targets.append(None)

        for language in language_targets:
            source_language = "mixed" if language is None else "ru"
            source_mode = "sensitive" if sensitive else "base"
            source = f"{source_language}-{source_mode}"
            candidate = self._transcribe_with_runtime_fallback(
                audio,
                language,
                source=source,
                sensitive=sensitive,
                disable_vad=disable_vad,
            )
            candidates.append(candidate)

        return candidates

    def transcribe(self, audio: np.ndarray) -> tuple[str, str | None]:
        if audio.size == 0:
            return "", None

        audio_rms = float(np.sqrt(np.mean(np.square(audio)) + 1e-9))
        if audio_rms < self.min_input_rms:
            return "", None

        duration_seconds = float(audio.size) / float(self.sample_rate)
        candidates = self._run_pass(audio, sensitive=False)
        if self.prefix_recovery_enabled and self.vad_filter and duration_seconds <= self.prefix_recovery_max_duration_seconds:
            candidates.extend(self._run_prefix_recovery_pass(audio))
        best_candidate = self._pick_best_candidate(candidates)

        if self._should_retry_low_confidence(best_candidate, duration_seconds):
            print("[stt] low-confidence transcript, running whisper-sensitive retry")
            candidates.extend(self._run_pass(audio, sensitive=True))
            boosted_audio = self._apply_audio_boost(audio)
            if self.audio_boost_enabled and not np.allclose(boosted_audio, audio):
                candidates.extend(self._run_pass(boosted_audio, sensitive=True))

        return self._build_primary_and_alternative(candidates)


class KeyboardTyper:
    def __init__(self, append_space: bool) -> None:
        self.append_space = append_space
        self.keyboard = keyboard.Controller()
        self._lock = threading.Lock()

    def type_text(self, text: str) -> None:
        if not text:
            return

        output = f"{text} " if self.append_space else text
        with self._lock:
            self.keyboard.type(output)


class SideVoiceTrayApp:
    def __init__(self, config: dict[str, Any], config_path: Path) -> None:
        self.config = config
        self.config_path = config_path

        sample_rate = int(config["audio"]["sample_rate"])
        channels = int(config["audio"]["channels"])
        self._sample_rate = sample_rate
        self._stt_config = dict(config["stt"])

        self.indicator = RecordingIndicator()
        self.recorder = AudioRecorder(sample_rate=sample_rate, channels=channels)
        self.transcriber: WhisperTranscriber | None = None
        self.typer = KeyboardTyper(append_space=bool(config["typing"]["append_space"]))

        self.recording_text = str(config["ui"]["recording_text"])
        self.processing_text = str(config["ui"]["processing_text"])

        hotkey_config = self.config.setdefault("hotkey", {})
        self._hotkey_mode = str(hotkey_config.get("mode", "mouse")).strip().lower()
        if self._hotkey_mode not in HOTKEY_MODES:
            self._hotkey_mode = "mouse"
            hotkey_config["mode"] = self._hotkey_mode

        self._hotkey_button = str(hotkey_config.get("mouse_button", "x1")).lower()
        if self._hotkey_button not in MOUSE_BUTTON_BY_NAME:
            self._hotkey_button = "x1"
            hotkey_config["mouse_button"] = self._hotkey_button

        self._keyboard_hotkey_combo = self._normalize_hotkey_combo(hotkey_config.get("keyboard_combo"))
        if len(self._keyboard_hotkey_combo) != 2:
            self._keyboard_hotkey_combo = ("ctrl", "space")
            hotkey_config["keyboard_combo"] = list(self._keyboard_hotkey_combo)
        self._keyboard_combo_max_interval = float(hotkey_config.get("keyboard_combo_timeout_seconds", 4.0))
        if self._keyboard_combo_max_interval <= 0:
            self._keyboard_combo_max_interval = 4.0
            hotkey_config["keyboard_combo_timeout_seconds"] = self._keyboard_combo_max_interval
        if self._hotkey_mode == "keyboard":
            hotkey_config["mode"] = self._hotkey_mode

        self._state_lock = threading.Lock()
        self._enabled = True
        self._recording = False
        self._processing = False
        self._loading_model = True
        self._startup_error: str | None = None
        self._binding_hotkey_mode: str | None = None
        self._binding_keyboard_keys: list[str] = []
        self._bind_started_at = 0.0
        self._stopping = False
        self._pressed_keyboard_keys: set[str] = set()
        self._recent_key_press_times: dict[str, float] = {}
        self._keyboard_sequence_keys: list[str] = []
        self._keyboard_sequence_started_at = 0.0
        self._keyboard_hotkey_latched = False
        self._keyboard_hotkey_block_until = 0.0

        self.icon: pystray.Icon | None = None
        self.mouse_listener: mouse.Listener | None = None
        self.keyboard_listener: keyboard.Listener | None = None
        self.settings_window: tk.Toplevel | None = None
        self._settings_error_var: tk.StringVar | None = None

    def _save_config(self) -> None:
        try:
            self.config_path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[config] unable to save config: {exc}")

    @staticmethod
    def _compose_hotkey_mode(*, mouse_enabled: bool, keyboard_enabled: bool) -> str:
        if mouse_enabled and keyboard_enabled:
            return "both"
        if keyboard_enabled:
            return "keyboard"
        return "mouse"

    def _mouse_hotkey_enabled(self) -> bool:
        return self._hotkey_mode in {"mouse", "both"}

    def _keyboard_hotkey_enabled(self) -> bool:
        return self._hotkey_mode in {"keyboard", "both"}

    def _normalize_hotkey_combo(self, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split("+")]
        elif isinstance(value, (list, tuple)):
            parts = [str(item).strip() for item in value]
        else:
            parts = []

        normalized: list[str] = []
        for part in parts:
            item = part.lower().replace(" ", "_")
            item = KEY_NAME_NORMALIZATION_MAP.get(item, item)
            if not item or item in normalized:
                continue
            normalized.append(item)
            if len(normalized) == 2:
                break
        return tuple(normalized)

    def _select_keyboard_binding_combo(self, keys: list[str]) -> tuple[str, str] | None:
        ordered: list[str] = []
        for key in keys:
            normalized = KEY_NAME_NORMALIZATION_MAP.get(key, key)
            if normalized and normalized not in ordered:
                ordered.append(normalized)

        if len(ordered) < 2:
            return None

        filtered = ordered
        non_noisy = [key for key in ordered if key not in NOISY_BIND_KEY_NAMES]
        if len(non_noisy) >= 2:
            filtered = non_noisy

        modifiers = [key for key in filtered if key in MODIFIER_KEY_NAMES]
        non_modifiers = [key for key in filtered if key not in MODIFIER_KEY_NAMES]

        if modifiers and non_modifiers:
            return modifiers[0], non_modifiers[0]
        return filtered[0], filtered[1]

    def _keyboard_combo_recently_pressed(self) -> bool:
        if len(self._keyboard_hotkey_combo) != 2:
            return False
        timestamps = [self._recent_key_press_times.get(key, 0.0) for key in self._keyboard_hotkey_combo]
        if any(timestamp <= 0.0 for timestamp in timestamps):
            return False
        return max(timestamps) - min(timestamps) <= self._keyboard_combo_max_interval

    def _reset_keyboard_sequence(self) -> None:
        self._keyboard_sequence_keys = []
        self._keyboard_sequence_started_at = 0.0

    def _register_keyboard_hotkey_step(self, key_name: str, now: float) -> bool:
        if not self._keyboard_hotkey_enabled() or len(self._keyboard_hotkey_combo) != 2:
            return False
        primary_key, secondary_key = self._keyboard_hotkey_combo
        modifier_style_combo = primary_key in MODIFIER_KEY_NAMES and secondary_key not in MODIFIER_KEY_NAMES
        if key_name not in self._keyboard_hotkey_combo:
            self._reset_keyboard_sequence()
            return False

        if modifier_style_combo and key_name == secondary_key and primary_key in self._pressed_keyboard_keys:
            self._reset_keyboard_sequence()
            return True

        if self._keyboard_sequence_started_at and now - self._keyboard_sequence_started_at > self._keyboard_combo_max_interval:
            self._reset_keyboard_sequence()

        if not self._keyboard_sequence_keys:
            if key_name != primary_key:
                return False
            self._keyboard_sequence_keys = [primary_key]
            self._keyboard_sequence_started_at = now
            return False

        if self._keyboard_sequence_keys == [primary_key]:
            if key_name == primary_key:
                self._keyboard_sequence_started_at = now
                return False
            if key_name == secondary_key:
                self._reset_keyboard_sequence()
                return True
            return False

        self._reset_keyboard_sequence()
        return False

    def _is_keyboard_hotkey_pressed(self) -> bool:
        if not self._keyboard_hotkey_enabled() or len(self._keyboard_hotkey_combo) != 2:
            return False
        return set(self._keyboard_hotkey_combo).issubset(self._pressed_keyboard_keys)

    def _format_keyboard_hotkey(self, combo: tuple[str, ...] | None = None) -> str:
        parts = combo or self._keyboard_hotkey_combo
        if not parts:
            return "Keyboard ?"
        return "Keyboard " + "+".join(hotkey_part_label(part) for part in parts)

    def _format_active_hotkey(self) -> str:
        if self._hotkey_mode == "both":
            return f"Mouse {self._hotkey_button.upper()} / {self._format_keyboard_hotkey()}"
        if self._keyboard_hotkey_enabled():
            return self._format_keyboard_hotkey()
        return f"Mouse {self._hotkey_button.upper()}"

    def _stt_ready(self) -> bool:
        return self.transcriber is not None and self._startup_error is None and not self._loading_model

    def _show_temporary_indicator(self, text: str, duration_seconds: float = 1.2) -> None:
        self.indicator.show(text)
        threading.Timer(duration_seconds, self.indicator.hide).start()

    def _hotkey_text(self) -> str:
        with self._state_lock:
            binding_mode = self._binding_hotkey_mode
            binding_keys = tuple(self._binding_keyboard_keys)
            hotkey_label = self._format_active_hotkey()
        if binding_mode == "mouse":
            return f"Hotkey: {hotkey_label} (waiting for click...)"
        if binding_mode == "keyboard":
            if binding_keys:
                return f"Hotkey: {hotkey_label} (binding: {'+'.join(hotkey_part_label(key) for key in binding_keys)})"
            return f"Hotkey: {hotkey_label} (waiting for 2 keys...)"
        return f"Hotkey: {hotkey_label}"

    def _pipeline_text(self) -> str:
        if self._startup_error is not None:
            return "Pipeline: startup error"
        if self.transcriber is None or self._loading_model:
            return "Pipeline: loading Whisper..."
        return f"Pipeline: Local Whisper ({self.transcriber.device.upper()})"

    def _status_text(self) -> str:
        with self._state_lock:
            if self._startup_error is not None:
                return "Status: startup error"
            if self._loading_model:
                return "Status: loading model"
            if self._binding_hotkey_mode is not None:
                return "Status: binding hotkey"
            if self._recording:
                return "Status: recording"
            if self._processing:
                return "Status: processing"
            return "Status: ready" if self._enabled else "Status: paused"

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _item: self._status_text(), lambda _icon, _item: None, enabled=False),
            pystray.MenuItem(lambda _item: self._hotkey_text(), lambda _icon, _item: None, enabled=False),
            pystray.MenuItem(lambda _item: self._pipeline_text(), lambda _icon, _item: None, enabled=False),
            pystray.MenuItem(
                "Settings",
                self._open_settings_from_tray,
                enabled=lambda _item: not self._recording and not self._processing and not self._stopping,
            ),
            pystray.MenuItem(
                "Bind Mouse Hotkey (next mouse click)",
                self._arm_mouse_hotkey_binding,
                enabled=lambda _item: not self._recording and not self._processing,
            ),
            pystray.MenuItem(
                "Bind Keyboard Hotkey (next 2 keys)",
                self._arm_keyboard_hotkey_binding,
                enabled=lambda _item: not self._recording and not self._processing,
            ),
            pystray.MenuItem(
                lambda _item: "Pause" if self._enabled else "Resume",
                self._toggle_enabled,
                enabled=lambda _item: not self._recording and not self._processing,
            ),
            pystray.MenuItem("Exit", self._exit_from_tray),
        )

    def _build_icon(self) -> Image.Image:
        with self._state_lock:
            active = self._recording or self._processing
            loading = self._loading_model
            error = self._startup_error is not None

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill="#111827", outline="#9ca3af", width=2)
        if error:
            color = "#f97316"
        elif active:
            color = "#ef4444"
        elif loading:
            color = "#facc15"
        else:
            color = "#22c55e"
        draw.ellipse((21, 21, 43, 43), fill=color)
        return image

    def _refresh_tray(self) -> None:
        if self.icon is None:
            return

        self.icon.icon = self._build_icon()
        self.icon.update_menu()

    def _toggle_enabled(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self._state_lock:
            if self._recording or self._processing or self._loading_model:
                return
            self._enabled = not self._enabled
        self._refresh_tray()

    def _open_settings_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.indicator.root.after(0, self._show_settings_window)

    def _exit_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.shutdown()

    def _close_settings_window(self) -> None:
        if self.settings_window is None:
            return
        try:
            self.settings_window.destroy()
        finally:
            self.settings_window = None
            self._settings_error_var = None

    def _show_settings_window(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self.indicator.root)
        window.title("SideVoiceTray Settings")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._close_settings_window)
        window.configure(padx=14, pady=14)
        self.settings_window = window
        self._settings_error_var = tk.StringVar(value="")

        hotkey_config = self.config.setdefault("hotkey", {})
        typing_config = self.config.setdefault("typing", {})
        ui_config = self.config.setdefault("ui", {})
        stt_config = self.config.setdefault("stt", {})

        mouse_enabled_var = tk.BooleanVar(value=self._mouse_hotkey_enabled())
        keyboard_enabled_var = tk.BooleanVar(value=self._keyboard_hotkey_enabled())
        append_space_var = tk.BooleanVar(value=bool(typing_config.get("append_space", True)))
        timeout_var = tk.StringVar(value=f"{self._keyboard_combo_max_interval:.2f}".rstrip("0").rstrip("."))
        recording_text_var = tk.StringVar(value=str(ui_config.get("recording_text", self.recording_text)))
        processing_text_var = tk.StringVar(value=str(ui_config.get("processing_text", self.processing_text)))
        keyboard_combo_var = tk.StringVar(value="+".join(self._keyboard_hotkey_combo))
        mouse_button_var = tk.StringVar(value=str(hotkey_config.get("mouse_button", self._hotkey_button)))

        form = tk.Frame(window)
        form.grid(row=0, column=0, sticky="nsew")

        def add_label(row: int, text: str) -> None:
            tk.Label(form, text=text, anchor="w", justify="left").grid(row=row, column=0, sticky="w", pady=(0, 4))

        add_label(0, "Active hotkeys")
        checkbox_row = tk.Frame(form)
        checkbox_row.grid(row=1, column=0, sticky="w", pady=(0, 10))
        tk.Checkbutton(checkbox_row, text="Mouse", variable=mouse_enabled_var).pack(side="left", padx=(0, 12))
        tk.Checkbutton(checkbox_row, text="Keyboard", variable=keyboard_enabled_var).pack(side="left")

        add_label(2, "Mouse button")
        mouse_options = list(MOUSE_BUTTON_BY_NAME.keys())
        tk.OptionMenu(form, mouse_button_var, *mouse_options).grid(row=3, column=0, sticky="ew", pady=(0, 10))

        add_label(4, "Keyboard combo (two keys, format: ctrl+])")
        tk.Entry(form, textvariable=keyboard_combo_var, width=28).grid(row=5, column=0, sticky="ew", pady=(0, 10))

        add_label(6, "Keyboard combo timeout (seconds)")
        tk.Entry(form, textvariable=timeout_var, width=12).grid(row=7, column=0, sticky="w", pady=(0, 10))

        add_label(8, "Recording text")
        tk.Entry(form, textvariable=recording_text_var, width=28).grid(row=9, column=0, sticky="ew", pady=(0, 10))

        add_label(10, "Processing text")
        tk.Entry(form, textvariable=processing_text_var, width=28).grid(row=11, column=0, sticky="ew", pady=(0, 10))

        tk.Checkbutton(form, text="Append trailing space after typed text", variable=append_space_var).grid(
            row=12, column=0, sticky="w", pady=(0, 10)
        )

        add_label(13, "Initial prompt")
        initial_prompt_text = tk.Text(form, width=56, height=5, wrap="word")
        initial_prompt_text.grid(row=14, column=0, sticky="ew", pady=(0, 10))
        initial_prompt_text.insert("1.0", str(stt_config.get("initial_prompt", "")))

        add_label(15, "Hotwords (comma-separated)")
        hotwords_text = tk.Text(form, width=56, height=6, wrap="word")
        hotwords_text.grid(row=16, column=0, sticky="ew", pady=(0, 10))
        hotwords_text.insert("1.0", ", ".join(stt_config.get("hotwords") or []))

        error_label = tk.Label(form, textvariable=self._settings_error_var, anchor="w", justify="left", fg="#b91c1c")
        error_label.grid(row=17, column=0, sticky="ew", pady=(0, 10))

        def save_settings() -> None:
            mouse_enabled = bool(mouse_enabled_var.get())
            keyboard_enabled = bool(keyboard_enabled_var.get())
            if not mouse_enabled and not keyboard_enabled:
                self._settings_error_var.set("Enable at least one hotkey.")
                return

            combo = self._normalize_hotkey_combo(keyboard_combo_var.get())
            if keyboard_enabled and len(combo) != 2:
                self._settings_error_var.set("Keyboard combo must contain exactly two keys.")
                return

            mouse_button = str(mouse_button_var.get()).strip().lower()
            if mouse_enabled and mouse_button not in MOUSE_BUTTON_BY_NAME:
                self._settings_error_var.set("Mouse button must be one of: left, right, middle, x1, x2.")
                return

            try:
                timeout_value = float(timeout_var.get().strip())
            except ValueError:
                self._settings_error_var.set("Keyboard timeout must be a number.")
                return
            if timeout_value <= 0:
                self._settings_error_var.set("Keyboard timeout must be greater than 0.")
                return

            recording_text = recording_text_var.get().strip() or "REC"
            processing_text = processing_text_var.get().strip() or "PROCESSING"
            initial_prompt = initial_prompt_text.get("1.0", "end").strip()
            raw_hotwords = hotwords_text.get("1.0", "end").strip()
            hotwords = [item.strip() for item in raw_hotwords.replace("\n", ",").split(",") if item.strip()]

            with self._state_lock:
                self._hotkey_mode = self._compose_hotkey_mode(
                    mouse_enabled=mouse_enabled,
                    keyboard_enabled=keyboard_enabled,
                )
                if mouse_enabled:
                    self._hotkey_button = mouse_button
                if keyboard_enabled:
                    self._keyboard_hotkey_combo = combo
                self._keyboard_combo_max_interval = timeout_value
                self._keyboard_hotkey_latched = False
                self._keyboard_hotkey_block_until = 0.0
                self._pressed_keyboard_keys.clear()
                self._reset_keyboard_sequence()

                self.recording_text = recording_text
                self.processing_text = processing_text
                self.typer.append_space = bool(append_space_var.get())

                hotkey_config["mode"] = self._hotkey_mode
                hotkey_config["mouse_button"] = self._hotkey_button
                hotkey_config["keyboard_combo"] = list(self._keyboard_hotkey_combo)
                hotkey_config["keyboard_combo_timeout_seconds"] = self._keyboard_combo_max_interval
                typing_config["append_space"] = self.typer.append_space
                ui_config["recording_text"] = self.recording_text
                ui_config["processing_text"] = self.processing_text
                stt_config["initial_prompt"] = initial_prompt or None
                stt_config["hotwords"] = hotwords
                self._stt_config = dict(stt_config)

            self._save_config()
            self._refresh_tray()
            self.indicator.show("SETTINGS SAVED")
            threading.Timer(1.0, self.indicator.hide).start()
            self._close_settings_window()

        buttons = tk.Frame(form)
        buttons.grid(row=18, column=0, sticky="e")
        tk.Button(buttons, text="Cancel", width=10, command=self._close_settings_window).pack(side="right")
        tk.Button(buttons, text="Save", width=10, command=save_settings).pack(side="right", padx=(0, 8))

        window.update_idletasks()
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        screen_x = window.winfo_screenwidth()
        screen_y = window.winfo_screenheight()
        x = max(40, (screen_x - width) // 2)
        y = max(40, (screen_y - height) // 2)
        window.geometry(f"+{x}+{y}")
        window.focus_force()

    def _arm_mouse_hotkey_binding(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self._state_lock:
            if self._recording or self._processing or self._stopping:
                return
            self._binding_hotkey_mode = "mouse"
            self._binding_keyboard_keys = []
            self._bind_started_at = time.monotonic()

        self.indicator.show("BIND HOTKEY: click mouse button")
        self._refresh_tray()

    def _arm_keyboard_hotkey_binding(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self._state_lock:
            if self._recording or self._processing or self._stopping:
                return
            self._binding_hotkey_mode = "keyboard"
            self._binding_keyboard_keys = []
            self._bind_started_at = time.monotonic()
            self._reset_keyboard_sequence()
            self._keyboard_hotkey_latched = False
            self._keyboard_hotkey_block_until = 0.0
            self._pressed_keyboard_keys.clear()

        self.indicator.show("BIND HOTKEY: press 2 keys")
        self._refresh_tray()

    def _finish_mouse_hotkey_binding(self, button: mouse.Button) -> None:
        button_name = MOUSE_NAME_BY_BUTTON.get(button)
        if button_name is None:
            return

        with self._state_lock:
            self._binding_hotkey_mode = None
            self._binding_keyboard_keys = []
            self._hotkey_button = button_name
            self._hotkey_mode = self._compose_hotkey_mode(
                mouse_enabled=True,
                keyboard_enabled=self._keyboard_hotkey_enabled(),
            )
            hotkey_config = self.config.setdefault("hotkey", {})
            hotkey_config["mode"] = self._hotkey_mode
            hotkey_config["mouse_button"] = button_name

        self._save_config()
        self.indicator.show(f"HOTKEY SET: {button_name.upper()}")
        threading.Timer(1.0, self.indicator.hide).start()
        self._refresh_tray()

    def _finish_keyboard_hotkey_binding(self, combo: tuple[str, str]) -> None:
        combo = tuple(combo[:2])
        if len(combo) != 2:
            return

        with self._state_lock:
            self._binding_hotkey_mode = None
            self._binding_keyboard_keys = []
            self._keyboard_hotkey_combo = combo
            self._reset_keyboard_sequence()
            self._keyboard_hotkey_latched = False
            self._keyboard_hotkey_block_until = time.monotonic() + 0.45
            self._pressed_keyboard_keys.clear()
            self._hotkey_mode = self._compose_hotkey_mode(
                mouse_enabled=self._mouse_hotkey_enabled(),
                keyboard_enabled=True,
            )
            hotkey_config = self.config.setdefault("hotkey", {})
            hotkey_config["mode"] = self._hotkey_mode
            hotkey_config["keyboard_combo"] = list(combo)

        self._save_config()
        self.indicator.show(f"HOTKEY SET: {'+'.join(hotkey_part_label(part) for part in combo)}")
        threading.Timer(1.0, self.indicator.hide).start()
        self._refresh_tray()

    def _matches_mouse_hotkey(self, button: mouse.Button) -> bool:
        if not self._mouse_hotkey_enabled():
            return False
        expected = MOUSE_BUTTON_BY_NAME.get(self._hotkey_button, mouse.Button.x1)
        return button == expected

    def _on_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed:
            return

        with self._state_lock:
            if self._binding_hotkey_mode == "mouse":
                started_at = self._bind_started_at
            else:
                started_at = 0.0

            if self._stopping:
                return

        if started_at:
            # Ignore the click that opened the tray menu action itself.
            if time.monotonic() - started_at < 0.35:
                return
            self._finish_mouse_hotkey_binding(button)
            return

        if not self._matches_mouse_hotkey(button):
            return

        with self._state_lock:
            if not self._enabled or self._processing:
                return
            if self._loading_model or self._startup_error is not None:
                should_notify_not_ready = True
                is_recording = False
            else:
                should_notify_not_ready = False
                is_recording = self._recording

        if should_notify_not_ready:
            if self._startup_error is not None:
                self._show_temporary_indicator("STARTUP ERROR", duration_seconds=2.5)
            else:
                self._show_temporary_indicator("LOADING MODEL...", duration_seconds=1.5)
            return

        if not is_recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        key_name = normalize_keyboard_key_name(key)
        if key_name is None:
            return

        now = time.monotonic()
        should_refresh_tray = False
        combo_to_bind: tuple[str, str] | None = None
        should_toggle = False
        should_start_recording = False

        with self._state_lock:
            self._pressed_keyboard_keys.add(key_name)
            self._recent_key_press_times[key_name] = now

            if self._binding_hotkey_mode == "keyboard":
                if key_name not in self._binding_keyboard_keys:
                    self._binding_keyboard_keys.append(key_name)
                    should_refresh_tray = True
                if len(self._binding_keyboard_keys) >= 2:
                    combo_to_bind = self._select_keyboard_binding_combo(self._binding_keyboard_keys)
            elif (
                now >= self._keyboard_hotkey_block_until
                and not self._keyboard_hotkey_latched
                and self._register_keyboard_hotkey_step(key_name, now)
            ):
                if not self._enabled or self._processing or self._stopping:
                    self._keyboard_hotkey_latched = True
                elif self._loading_model or self._startup_error is not None:
                    should_refresh_tray = False
                    should_toggle = False
                    self._keyboard_hotkey_latched = True
                else:
                    should_toggle = True
                    should_start_recording = not self._recording
                    self._keyboard_hotkey_latched = True

        if should_refresh_tray:
            self._refresh_tray()

        if combo_to_bind is not None:
            self._finish_keyboard_hotkey_binding(combo_to_bind)
            return

        if self._keyboard_hotkey_latched and (self._loading_model or self._startup_error is not None) and not should_toggle:
            if self._startup_error is not None:
                self._show_temporary_indicator("STARTUP ERROR", duration_seconds=2.5)
            else:
                self._show_temporary_indicator("LOADING MODEL...", duration_seconds=1.5)
            return

        if not should_toggle:
            return

        if should_start_recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        key_name = normalize_keyboard_key_name(key)
        if key_name is None:
            return

        with self._state_lock:
            self._pressed_keyboard_keys.discard(key_name)
            if not self._is_keyboard_hotkey_pressed():
                self._keyboard_hotkey_latched = False

    def _start_recording(self) -> None:
        if not self._stt_ready():
            if self._startup_error is not None:
                self._show_temporary_indicator("STARTUP ERROR", duration_seconds=2.5)
            else:
                self._show_temporary_indicator("LOADING MODEL...", duration_seconds=1.5)
            return

        try:
            self.recorder.start()
        except Exception as exc:
            print(f"[audio] unable to start recording: {exc}")
            return

        with self._state_lock:
            self._recording = True

        self.indicator.show(self.recording_text)
        self._refresh_tray()

    def _stop_recording_and_process(self) -> None:
        audio = self.recorder.stop()

        with self._state_lock:
            self._recording = False
            self._processing = True

        self.indicator.show(self.processing_text)
        self._refresh_tray()

        worker = threading.Thread(target=self._process_audio, args=(audio,), daemon=True)
        worker.start()

    def _process_audio(self, audio: np.ndarray) -> None:
        try:
            if audio.size == 0:
                return

            transcriber = self.transcriber
            if transcriber is None:
                return

            raw_text, _alternative_text = transcriber.transcribe(audio)
            if not raw_text:
                return

            final_text = normalize_whisper_output(raw_text)
            self.typer.type_text(final_text)
        except Exception as exc:
            print(f"[pipeline] error: {exc}")
        finally:
            with self._state_lock:
                self._processing = False
            self.indicator.hide()
            self._refresh_tray()

    def _load_transcriber_worker(self) -> None:
        try:
            transcriber = WhisperTranscriber(config=self._stt_config, sample_rate=self._sample_rate)
        except Exception as exc:
            print(f"[stt] startup failed: {exc}")
            with self._state_lock:
                self._startup_error = str(exc)
                self._loading_model = False
            self.indicator.show("STARTUP ERROR")
            self._refresh_tray()
            return

        with self._state_lock:
            self.transcriber = transcriber
            self._loading_model = False
            self._startup_error = None

        self.indicator.hide()
        self._refresh_tray()

    def _start_transcriber_loading(self) -> None:
        self.indicator.show("LOADING WHISPER...")
        worker = threading.Thread(target=self._load_transcriber_worker, daemon=True)
        worker.start()

    def _start_mouse_listener(self) -> None:
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.mouse_listener.start()

    def _start_keyboard_listener(self) -> None:
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self.keyboard_listener.start()

    def _start_tray(self) -> None:
        self.icon = pystray.Icon(
            "side-voice-tray",
            self._build_icon(),
            "SideVoiceTray",
            self._menu(),
        )
        self.icon.run_detached()

    def shutdown(self) -> None:
        with self._state_lock:
            if self._stopping:
                return
            self._stopping = True

        self.indicator.root.after(0, self._close_settings_window)

        try:
            self.recorder.stop()
        except Exception:
            pass

        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()

        if self.icon is not None:
            self.icon.stop()

        self.indicator.stop()

    def run(self) -> None:
        self._start_tray()
        self._start_transcriber_loading()
        self._start_mouse_listener()
        self._start_keyboard_listener()
        self.indicator.run()


def main() -> int:
    if not acquire_single_instance_mutex():
        print("[app] already running, skipping second instance")
        return 2

    base_dir = get_app_base_dir()
    config_path = base_dir / "config.json"

    config = load_config(config_path)
    app = SideVoiceTrayApp(config=config, config_path=config_path)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
