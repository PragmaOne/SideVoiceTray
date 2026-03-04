from __future__ import annotations

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
import requests
import sounddevice as sd
import tkinter as tk
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw
from pynput import keyboard, mouse

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

_DLL_DIR_HANDLES: list[Any] = []
_REGISTERED_DLL_DIRS: set[str] = set()


DEFAULT_CONFIG: dict[str, Any] = {
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
    },
    "stt": {
        "model": "large-v3",
        "device": "auto",
        "compute_type": "float16",
        "language": "ru",
        "beam_size": 12,
        "best_of": 12,
        "patience": 1.3,
        "temperature": 0.0,
        "repetition_penalty": 1.0,
        "condition_on_previous_text": True,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.45,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": 0.45,
            "min_speech_duration_ms": 120,
            "min_silence_duration_ms": 380,
            "speech_pad_ms": 230,
        },
        "mixed_language_fallback": False,
        "language_detection_threshold": 0.4,
        "language_detection_segments": 3,
        "whisper_rescue_enabled": True,
        "low_confidence_avg_logprob": -1.0,
        "low_confidence_no_speech_prob": 0.75,
        "audio_boost_enabled": False,
        "target_rms": 0.09,
        "max_gain_db": 28.0,
        "min_input_rms": 0.00045,
        "retry_without_vad": True,
        "sensitive_beam_size": 16,
        "sensitive_best_of": 16,
        "sensitive_patience": 2.0,
        "sensitive_no_speech_threshold": 0.28,
        "sensitive_log_prob_threshold": -1.35,
        "initial_prompt": None,
        "hotwords": [
            "Python",
            "Docker",
            "GitHub",
            "API",
            "SQL",
            "JavaScript",
            "TypeScript",
            "Windows",
            "Telegram",
            "YouTube",
            "OpenAI",
            "LM Studio",
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
    "lm_studio": {
        "enabled": True,
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "qwen2.5-7b-instruct",
        "temperature": 0.0,
        "max_output_tokens": 1500,
        "repair_retries": 4,
        "quality_second_pass": True,
        "quality_refine_passes": 3,
        "timeout_seconds": 90,
    },
    "hotkey": {
        "mouse_button": "x1",
    },
    "typing": {
        "append_space": True,
    },
    "output": {
        "target_language": "none",
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
OUTPUT_LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("none", "Russian (No translation)"),
    ("en", "English"),
    ("es", "Spanish"),
    ("pl", "Polish"),
    ("zh", "Chinese (Simplified)"),
]
OUTPUT_LANGUAGE_LABELS: dict[str, str] = {code: label for code, label in OUTPUT_LANGUAGE_OPTIONS}
TRANSLATION_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "pl": "Polish",
    "zh": "Chinese (Simplified)",
}
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


def configure_windows_cuda_runtime() -> None:
    if os.name != "nt":
        return

    candidates = [
        Path(sys.prefix) / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
    ]

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
        self.sample_rate = sample_rate
        self.language = self._normalize_language(config.get("language"))
        self.beam_size = int(config["beam_size"])
        self.best_of = int(config.get("best_of", self.beam_size))
        self.patience = float(config.get("patience", 1.0))
        self.decode_temperature = float(config.get("temperature", 0.0))
        self.repetition_penalty = float(config.get("repetition_penalty", 1.0))
        self.condition_on_previous_text = bool(config.get("condition_on_previous_text", True))
        self.compression_ratio_threshold = float(config.get("compression_ratio_threshold", 2.4))
        self.log_prob_threshold = float(config.get("log_prob_threshold", -1.0))
        self.no_speech_threshold = float(config.get("no_speech_threshold", 0.45))
        self.vad_filter = bool(config["vad_filter"])
        self.vad_parameters = config.get("vad_parameters")
        self.mixed_language_fallback = bool(config.get("mixed_language_fallback", True))
        self.language_detection_threshold = float(config.get("language_detection_threshold", 0.4))
        self.language_detection_segments = int(config.get("language_detection_segments", 3))
        self.whisper_rescue_enabled = bool(config.get("whisper_rescue_enabled", True))
        self.low_confidence_avg_logprob = float(config.get("low_confidence_avg_logprob", -1.05))
        self.low_confidence_no_speech_prob = float(config.get("low_confidence_no_speech_prob", 0.72))
        self.audio_boost_enabled = bool(config.get("audio_boost_enabled", True))
        self.target_rms = float(config.get("target_rms", 0.09))
        self.max_gain_db = float(config.get("max_gain_db", 28.0))
        self.max_linear_gain = float(10.0 ** (self.max_gain_db / 20.0))
        self.min_input_rms = float(config.get("min_input_rms", 0.0012))
        self.retry_without_vad = bool(config.get("retry_without_vad", True))
        self.sensitive_beam_size = int(config.get("sensitive_beam_size", max(self.beam_size, 12)))
        self.sensitive_best_of = int(config.get("sensitive_best_of", max(self.best_of, 12)))
        self.sensitive_patience = float(config.get("sensitive_patience", max(self.patience, 1.8)))
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

        print("[stt] loading Whisper model...")
        self.model = self._load_model_with_compute_fallback()
        print(f"[stt] Whisper model ready (device={self.device})")

    def _load_model_with_compute_fallback(self) -> WhisperModel:
        attempts: list[str] = [self.compute_type]
        if self.compute_type == "float16":
            attempts.extend(["int8_float16", "int8"])
        elif self.compute_type == "float32":
            attempts.append("int8")
        elif self.compute_type == "auto":
            attempts.append("int8")

        last_error: Exception | None = None
        seen: set[str] = set()
        for compute_type in attempts:
            if compute_type in seen:
                continue
            seen.add(compute_type)
            try:
                model = WhisperModel(
                    model_size_or_path=self.model_name,
                    device=self.device,
                    compute_type=compute_type,
                )
                self.compute_type = compute_type
                return model
            except Exception as exc:
                last_error = exc
                print(f"[stt] compute_type {compute_type} unavailable, retrying...")

        if last_error is not None:
            raise last_error
        raise RuntimeError("Unable to load Whisper model")

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
        no_speech_threshold = self.sensitive_no_speech_threshold if sensitive else self.no_speech_threshold
        log_prob_threshold = self.sensitive_log_prob_threshold if sensitive else self.log_prob_threshold

        kwargs: dict[str, Any] = {
            "language": language,
            "task": "transcribe",
            "beam_size": beam_size,
            "best_of": best_of,
            "patience": patience,
            "temperature": self.decode_temperature,
            "repetition_penalty": self.repetition_penalty,
            "condition_on_previous_text": self.condition_on_previous_text,
            "compression_ratio_threshold": self.compression_ratio_threshold,
            "log_prob_threshold": log_prob_threshold,
            "no_speech_threshold": no_speech_threshold,
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
                    model_size_or_path=self.model_name,
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
        if not self.whisper_rescue_enabled or duration_seconds < 0.8:
            return False
        if best_candidate is None:
            return True
        if best_candidate.avg_logprob < self.low_confidence_avg_logprob:
            return True
        if best_candidate.no_speech_prob > self.low_confidence_no_speech_prob:
            short_text = len(best_candidate.text) < max(8, int(duration_seconds * 4))
            if short_text:
                return True
        return False

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

        ranked = sorted(best_per_text.values(), key=lambda item: item[1], reverse=True)
        primary_text = ranked[0][0].text
        alternative_text = ranked[1][0].text if len(ranked) > 1 else None
        return primary_text, alternative_text

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
        best_candidate = self._pick_best_candidate(candidates)

        if self._should_retry_low_confidence(best_candidate, duration_seconds):
            print("[stt] low-confidence transcript, running whisper-sensitive retry")
            boosted_audio = self._apply_audio_boost(audio)
            candidates.extend(self._run_pass(boosted_audio, sensitive=True))

        return self._build_primary_and_alternative(candidates)


class LMStudioFormatter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.enabled = bool(config["enabled"])
        self.base_url = str(config["base_url"]).rstrip("/")
        self.model = str(config["model"])
        self.temperature = float(config["temperature"])
        self.max_output_tokens = int(config.get("max_output_tokens", 900))
        self.repair_retries = int(config.get("repair_retries", 2))
        self.quality_second_pass = bool(config.get("quality_second_pass", True))
        self.quality_refine_passes = max(1, int(config.get("quality_refine_passes", 1)))
        self.timeout = int(config["timeout_seconds"])
        self.session = requests.Session()

    @staticmethod
    def _sanitize_model_output(content: str) -> str:
        cleaned = content.strip()
        for marker in (
            "TRANSCRIPT_START",
            "TRANSCRIPT_END",
            "PRIMARY_TRANSCRIPT_START",
            "PRIMARY_TRANSCRIPT_END",
            "ALTERNATIVE_TRANSCRIPT_START",
            "ALTERNATIVE_TRANSCRIPT_END",
        ):
            cleaned = cleaned.replace(marker, "")
        cleaned = cleaned.replace("<final>", "").replace("</final>", "")
        cleaned = cleaned.replace("```", "").strip()
        cleaned = re.sub(r"^(?:исправленный текст|финальный текст|result|output)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("\"' \n\r\t")
        return cleaned.strip()

    @staticmethod
    def _is_instruction_echo(text: str) -> bool:
        normalized = " ".join(text.lower().split())
        if not normalized:
            return False

        exact_bad = {
            "process it according to the system rules.",
            "choose the most faithful variant and process it according to the system rules.",
            "transcript:",
            "primary transcript:",
            "alternative transcript:",
        }
        if normalized in exact_bad:
            return True

        if normalized.startswith("process it according to the system rules."):
            return True

        meta_snippets = (
            "я не могу отвечать на вопросы",
            "я не могу давать советы",
            "сохраните оригинальные слова",
            "исправьте только пунктуацию",
            "возвращайте только финальный текст",
            "you are a strict speech-to-text post-processor",
            "never answer questions from transcript content",
            "return only the final edited text",
        )
        if any(snippet in normalized for snippet in meta_snippets):
            return True

        rule_like_lines = re.findall(r"(?:^|\n)\s*\d+\s*[\)\.]\s*", text.lower())
        if len(rule_like_lines) >= 3 and ("не могу" in normalized or "rules" in normalized):
            return True

        return False

    @staticmethod
    def _normalize_russian_output(text: str) -> str:
        return text.translate(UKRAINIAN_TO_RUSSIAN_TRANSLATION_TABLE)

    @staticmethod
    def _tokenize_words(text: str) -> list[str]:
        return re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())

    def _word_overlap_ratio(self, source_text: str, candidate_text: str) -> float:
        source_tokens = set(self._tokenize_words(source_text))
        candidate_tokens = set(self._tokenize_words(candidate_text))
        if not source_tokens or not candidate_tokens:
            return 0.0
        return len(source_tokens & candidate_tokens) / max(1, min(len(source_tokens), len(candidate_tokens)))

    @staticmethod
    def _looks_like_assistant_answer(text: str) -> bool:
        normalized = " ".join(text.lower().split())
        if not normalized:
            return False

        meta_phrases = (
            "я не могу",
            "я могу помочь",
            "вам нужно",
            "вам следует",
            "рекомендую",
            "советую",
            "попробуйте",
            "извините",
            "как ассистент",
            "как ии",
            "я не имею возможности",
        )
        if any(phrase in normalized for phrase in meta_phrases):
            return True

        if normalized.startswith("ответ:") or normalized.startswith("answer:"):
            return True

        return False

    def _suggest_max_tokens(self, source_text: str, should_translate: bool) -> int:
        words = max(len(source_text.split()), 1)
        base = 160 if should_translate else 120
        per_word = 4 if should_translate else 3
        suggested = base + (words * per_word)
        return max(80, min(self.max_output_tokens, suggested))

    def _chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return self._sanitize_model_output(data["choices"][0]["message"]["content"])

    def _is_valid_result(
        self,
        result: str,
        source_text: str,
        *,
        should_translate: bool,
        alternative_text: str | None = None,
    ) -> bool:
        if not result:
            return False
        if self._is_instruction_echo(result):
            return False
        if len(result) > max(1200, len(source_text) * 4 + 120):
            return False

        if should_translate:
            return True

        source_len = max(len(source_text), 1)
        if len(result) < max(3, int(source_len * 0.35)):
            return False
        if len(result) > int(source_len * 2.7) + 80:
            return False

        overlap_main = self._word_overlap_ratio(source_text, result)
        overlap_alt = self._word_overlap_ratio(alternative_text or "", result)
        best_overlap = max(overlap_main, overlap_alt)
        if best_overlap < 0.34:
            return False

        if self._looks_like_assistant_answer(result) and best_overlap < 0.7:
            return False

        return True

    def _score_russian_candidate(
        self,
        candidate: str,
        source_text: str,
        alternative_text: str | None,
    ) -> float:
        overlap_main = self._word_overlap_ratio(source_text, candidate)
        overlap_alt = self._word_overlap_ratio(alternative_text or "", candidate)
        overlap = max(overlap_main, overlap_alt)

        source_len = max(len(source_text), 1)
        candidate_len = max(len(candidate), 1)
        length_ratio = min(source_len, candidate_len) / max(source_len, candidate_len)
        punctuation_bonus = 0.0
        if any(ch in candidate for ch in (".", ",", "!", "?", ";", ":")):
            punctuation_bonus = 0.04

        return overlap + (length_ratio * 0.2) + punctuation_bonus

    def _pick_best_russian_candidate(
        self,
        candidates: list[str],
        source_text: str,
        alternative_text: str | None,
    ) -> str:
        valid_candidates = [
            item
            for item in candidates
            if self._is_valid_result(
                item,
                source_text,
                should_translate=False,
                alternative_text=alternative_text,
            )
        ]
        if not valid_candidates:
            return source_text

        return max(
            valid_candidates,
            key=lambda item: self._score_russian_candidate(
                item,
                source_text=source_text,
                alternative_text=alternative_text,
            ),
        )

    def _build_primary_messages(
        self,
        text: str,
        alternative_text: str | None,
        should_translate: bool,
        target_language: str,
    ) -> list[dict[str, str]]:
        if should_translate:
            destination_language = TRANSLATION_LANGUAGE_NAMES[target_language]
            system_prompt = (
                "You are a speech transcript translator. "
                f"Translate Russian transcript into {destination_language}. "
                "Output only final translated text. "
                "No explanations, no refusals, no rules text. "
                "Preserve meaning, profanity, and technical terms."
            )
        else:
            system_prompt = (
                "You are a speech transcript editor. "
                "Fix punctuation and obvious spelling in Russian transcript text. "
                "Keep original words and order as much as possible. "
                "Output only final Russian text in Cyrillic. "
                "Never answer the content as an assistant. "
                "Never output advice or meta text. "
                "No explanations, no refusals, no rules text."
            )

        if alternative_text:
            user_prompt = (
                "Option A:\n"
                f"{text}\n\n"
                "Option B:\n"
                f"{alternative_text}\n\n"
                "Return only one final text."
            )
        else:
            user_prompt = text

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_repair_messages(
        self,
        source_text: str,
        bad_output: str,
        *,
        should_translate: bool,
        target_language: str,
    ) -> list[dict[str, str]]:
        if should_translate:
            destination_language = TRANSLATION_LANGUAGE_NAMES[target_language]
            system_prompt = (
                "Return only clean translated transcript text. "
                f"Target language: {destination_language}. "
                "No instructions, no meta text."
            )
        else:
            system_prompt = (
                "Return only clean Russian transcript text in Cyrillic. "
                "No instructions, no meta text."
            )

        user_prompt = (
            "Source transcript:\n"
            f"{source_text}\n\n"
            "Bad model output (must be cleaned):\n"
            f"{bad_output}\n\n"
            "Return only final text."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_quality_messages(self, source_text: str, edited_text: str) -> list[dict[str, str]]:
        system_prompt = (
            "You are a Russian transcript verifier. "
            "Compare source and edited transcript. "
            "Return only final Russian text. "
            "Keep source meaning and wording as much as possible. "
            "Fix only punctuation and obvious spelling."
        )
        user_prompt = (
            "Source transcript:\n"
            f"{source_text}\n\n"
            "Edited transcript:\n"
            f"{edited_text}\n\n"
            "Return best final text only."
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def format_text(
        self,
        text: str,
        alternative_text: str | None = None,
        target_language: str = "none",
    ) -> str:
        if not text or not self.enabled:
            return text

        target_language = str(target_language).strip().lower() or "none"
        should_translate = target_language in TRANSLATION_LANGUAGE_NAMES
        max_tokens = self._suggest_max_tokens(text, should_translate=should_translate)
        primary_messages = self._build_primary_messages(
            text=text,
            alternative_text=alternative_text,
            should_translate=should_translate,
            target_language=target_language,
        )

        try:
            content = self._chat_completion(primary_messages, max_tokens=max_tokens)
            if not should_translate:
                content = self._normalize_russian_output(content)

            if self._is_valid_result(
                content,
                text,
                should_translate=should_translate,
                alternative_text=alternative_text,
            ):
                if self.quality_second_pass and not should_translate:
                    candidates = [content]
                    refined = content
                    for _ in range(self.quality_refine_passes):
                        quality_messages = self._build_quality_messages(source_text=text, edited_text=refined)
                        quality_output = self._chat_completion(
                            quality_messages,
                            max_tokens=max_tokens,
                            temperature=0.0,
                        )
                        quality_output = self._normalize_russian_output(quality_output)
                        if not self._is_valid_result(
                            quality_output,
                            text,
                            should_translate=should_translate,
                            alternative_text=alternative_text,
                        ):
                            break
                        candidates.append(quality_output)
                        refined = quality_output
                    return self._pick_best_russian_candidate(
                        candidates,
                        source_text=text,
                        alternative_text=alternative_text,
                    )
                return content

            candidate = content
            for _ in range(self.repair_retries):
                repair_messages = self._build_repair_messages(
                    source_text=text,
                    bad_output=candidate,
                    should_translate=should_translate,
                    target_language=target_language,
                )
                candidate = self._chat_completion(repair_messages, max_tokens=max_tokens, temperature=0.0)
                if not should_translate:
                    candidate = self._normalize_russian_output(candidate)
                if self._is_valid_result(
                    candidate,
                    text,
                    should_translate=should_translate,
                    alternative_text=alternative_text,
                ):
                    return candidate

            if not should_translate:
                return self._normalize_russian_output(text)
            return text
        except Exception as exc:
            print(f"[lm-studio] formatting fallback: {exc}")
            if not should_translate:
                return self._normalize_russian_output(text)
            return text


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

        self.indicator = RecordingIndicator()
        self.recorder = AudioRecorder(sample_rate=sample_rate, channels=channels)
        self.transcriber = WhisperTranscriber(config=config["stt"], sample_rate=sample_rate)
        self.formatter = LMStudioFormatter(config=config["lm_studio"])
        self.typer = KeyboardTyper(append_space=bool(config["typing"]["append_space"]))

        self.recording_text = str(config["ui"]["recording_text"])
        self.processing_text = str(config["ui"]["processing_text"])
        self._target_language = str(config.get("output", {}).get("target_language", "none")).strip().lower()
        if self._target_language not in OUTPUT_LANGUAGE_LABELS:
            self._target_language = "none"
            self.config.setdefault("output", {})["target_language"] = self._target_language

        self._hotkey_button = str(config["hotkey"]["mouse_button"]).lower()
        if self._hotkey_button not in MOUSE_BUTTON_BY_NAME:
            self._hotkey_button = "x1"
            self.config["hotkey"]["mouse_button"] = self._hotkey_button

        self._state_lock = threading.Lock()
        self._enabled = True
        self._recording = False
        self._processing = False
        self._binding_hotkey = False
        self._bind_started_at = 0.0
        self._stopping = False

        self.icon: pystray.Icon | None = None
        self.mouse_listener: mouse.Listener | None = None

    def _save_config(self) -> None:
        try:
            self.config_path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[config] unable to save config: {exc}")

    def _hotkey_text(self) -> str:
        with self._state_lock:
            hotkey = self._hotkey_button.upper()
            binding = self._binding_hotkey
        if binding:
            return f"Hotkey: {hotkey} (waiting for click...)"
        return f"Hotkey: {hotkey}"

    def _output_mode_text(self) -> str:
        with self._state_lock:
            label = OUTPUT_LANGUAGE_LABELS.get(self._target_language, OUTPUT_LANGUAGE_LABELS["none"])
        return f"Output: {label}"

    def _is_output_language_selected(self, language_code: str) -> bool:
        with self._state_lock:
            return self._target_language == language_code

    def _set_output_language(self, language_code: str) -> None:
        if language_code not in OUTPUT_LANGUAGE_LABELS:
            return

        with self._state_lock:
            self._target_language = language_code
            self.config.setdefault("output", {})["target_language"] = language_code

        self._save_config()
        self.indicator.show(f"OUTPUT: {OUTPUT_LANGUAGE_LABELS[language_code]}")
        threading.Timer(1.0, self.indicator.hide).start()
        self._refresh_tray()

    def _make_output_language_handler(self, language_code: str):
        def _handler(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
            self._set_output_language(language_code)

        return _handler

    def _status_text(self) -> str:
        with self._state_lock:
            if self._binding_hotkey:
                return "Status: binding hotkey"
            if self._recording:
                return "Status: recording"
            if self._processing:
                return "Status: processing"
            return "Status: ready" if self._enabled else "Status: paused"

    def _menu(self) -> pystray.Menu:
        output_language_items = [
            pystray.MenuItem(
                label,
                self._make_output_language_handler(language_code),
                checked=lambda _item, code=language_code: self._is_output_language_selected(code),
                radio=True,
                enabled=lambda _item: not self._recording and not self._processing,
            )
            for language_code, label in OUTPUT_LANGUAGE_OPTIONS
        ]

        return pystray.Menu(
            pystray.MenuItem(lambda _item: self._status_text(), lambda _icon, _item: None, enabled=False),
            pystray.MenuItem(lambda _item: self._hotkey_text(), lambda _icon, _item: None, enabled=False),
            pystray.MenuItem(lambda _item: self._output_mode_text(), lambda _icon, _item: None, enabled=False),
            *output_language_items,
            pystray.MenuItem(
                "Bind Hotkey (next mouse click)",
                self._arm_hotkey_binding,
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

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill="#111827", outline="#9ca3af", width=2)
        color = "#ef4444" if active else "#22c55e"
        draw.ellipse((21, 21, 43, 43), fill=color)
        return image

    def _refresh_tray(self) -> None:
        if self.icon is None:
            return

        self.icon.icon = self._build_icon()
        self.icon.update_menu()

    def _toggle_enabled(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self._state_lock:
            if self._recording or self._processing:
                return
            self._enabled = not self._enabled
        self._refresh_tray()

    def _exit_from_tray(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.shutdown()

    def _arm_hotkey_binding(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self._state_lock:
            if self._recording or self._processing or self._stopping:
                return
            self._binding_hotkey = True
            self._bind_started_at = time.monotonic()

        self.indicator.show("BIND HOTKEY: click mouse button")
        self._refresh_tray()

    def _finish_hotkey_binding(self, button: mouse.Button) -> None:
        button_name = MOUSE_NAME_BY_BUTTON.get(button)
        if button_name is None:
            return

        with self._state_lock:
            self._binding_hotkey = False
            self._hotkey_button = button_name
            self.config["hotkey"]["mouse_button"] = button_name

        self._save_config()
        self.indicator.show(f"HOTKEY SET: {button_name.upper()}")
        threading.Timer(1.0, self.indicator.hide).start()
        self._refresh_tray()

    def _matches_hotkey(self, button: mouse.Button) -> bool:
        expected = MOUSE_BUTTON_BY_NAME.get(self._hotkey_button, mouse.Button.x1)
        return button == expected

    def _on_mouse_click(self, _x: int, _y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed:
            return

        with self._state_lock:
            if self._binding_hotkey:
                started_at = self._bind_started_at
            else:
                started_at = 0.0

            if self._stopping:
                return

        if started_at:
            # Ignore the click that opened the tray menu action itself.
            if time.monotonic() - started_at < 0.35:
                return
            self._finish_hotkey_binding(button)
            return

        if not self._matches_hotkey(button):
            return

        with self._state_lock:
            if not self._enabled or self._processing:
                return
            is_recording = self._recording

        if not is_recording:
            self._start_recording()
        else:
            self._stop_recording_and_process()

    def _start_recording(self) -> None:
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

            raw_text, alternative_text = self.transcriber.transcribe(audio)
            if not raw_text:
                return

            with self._state_lock:
                target_language = self._target_language

            final_text = self.formatter.format_text(
                raw_text,
                alternative_text=alternative_text,
                target_language=target_language,
            )
            self.typer.type_text(final_text)
        except Exception as exc:
            print(f"[pipeline] error: {exc}")
        finally:
            with self._state_lock:
                self._processing = False
            self.indicator.hide()
            self._refresh_tray()

    def _start_mouse_listener(self) -> None:
        self.mouse_listener = mouse.Listener(on_click=self._on_mouse_click)
        self.mouse_listener.start()

    def _start_tray(self) -> None:
        self.icon = pystray.Icon(
            "side-voice-tray",
            self._build_icon(),
            "SideVoiceTray",
            self._menu(),
        )
        tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        tray_thread.start()

    def shutdown(self) -> None:
        with self._state_lock:
            if self._stopping:
                return
            self._stopping = True

        try:
            self.recorder.stop()
        except Exception:
            pass

        if self.mouse_listener is not None:
            self.mouse_listener.stop()

        if self.icon is not None:
            self.icon.stop()

        self.indicator.stop()

    def run(self) -> None:
        self._start_mouse_listener()
        self._start_tray()
        self.indicator.run()


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    config_path = base_dir / "config.json"

    config = load_config(config_path)
    app = SideVoiceTrayApp(config=config, config_path=config_path)

    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()


if __name__ == "__main__":
    main()
