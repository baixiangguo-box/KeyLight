"""System-audio (WASAPI loopback) capture turned into LED band levels."""

from __future__ import annotations

import math
import threading
import time

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None

try:
    import pyaudiowpatch as pyaudio
except Exception:  # noqa: BLE001
    pyaudio = None

BANDS = 22
FFT_SIZE = 2048
LOW_HZ = 45.0
HIGH_HZ = 16000.0


class RhythmTracker:
    """Transient-driven flashes; steady sound never generates clock-based beats."""

    def __init__(self):
        self.pulse = self.energy = 0.0
        self.beat_count = 0
        self._rms = self._bass = self._average = 0.0
        self._flux_average = 0.0
        self._time = 0.0
        self._last_beat = -1.0

    def update(self, rms: float, bass: float, flux: float, dt: float) -> None:
        self._time += dt
        self.pulse *= math.exp(-dt / 0.13)
        audible = rms > 0.0018  # Gate quiet background noise before normalization.
        level = max(0.0, min(1.0, (20 * math.log10(max(rms, 1e-7)) + 55) / 45)) if audible else 0.0
        self.energy = max(level, self.energy * math.exp(-dt / 0.10))
        strength = max((rms - self._rms) / max(.008, self._average * .7),
                       (bass - self._bass) / max(.008, self._average * .7),
                       max(0, flux - self._flux_average * 1.5) / max(.012, self._average * .9))
        if audible and strength > .25 and self._time - self._last_beat >= .14:
            self.pulse = max(self.pulse, min(1.0, .55 + .45 * strength))
            self.beat_count += 1
            self._last_beat = self._time
        self._average += (rms - self._average) * (1 - math.exp(-dt / .6))
        self._flux_average += (flux - self._flux_average) * (1 - math.exp(-dt / .6))
        self._rms, self._bass = rms, bass


class AudioAnalyzer(threading.Thread):
    """Captures the default playback device (loopback) and exposes 22 band levels."""

    def __init__(self, bands: int = BANDS):
        super().__init__(name="audio-loop", daemon=True)
        self.bands = bands
        self.levels = [0.0] * bands
        self.rms = 0.0
        self.active = False
        self.error: str | None = None
        self.device_name: str | None = None
        self.device_index: int | None = None
        self.gain = 1.0
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._buffer = None
        self._pa = None
        self._stream = None
        self._edges = self._band_edges()
        self._rhythm = RhythmTracker()
        self._last_update: float | None = None
        self._previous_spectrum = None

    # ------------------------------------------------------------------ api
    @staticmethod
    def available() -> bool:
        return pyaudio is not None and np is not None

    @staticmethod
    def list_devices() -> list[dict]:
        if pyaudio is None:
            return []
        out: list[dict] = []
        pa = None
        try:
            pa = pyaudio.PyAudio()
            default = None
            try:
                default = pa.get_default_wasapi_loopback()
            except Exception:  # noqa: BLE001
                pass
            for info in pa.get_loopback_device_info_generator():
                out.append({
                    "index": int(info["index"]),
                    "name": str(info["name"]),
                    "rate": int(info.get("defaultSampleRate") or 48000),
                    "channels": int(info.get("maxInputChannels") or 2),
                    "default": bool(default and info["index"] == default["index"]),
                })
        except Exception:  # noqa: BLE001
            return out
        finally:
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:  # noqa: BLE001
                    pass
        return out

    def set_gain(self, gain: float) -> None:
        self.gain = max(0.1, min(6.0, float(gain)))

    # -------------------------------------------------------------- filters
    def _band_edges(self) -> list[tuple[int, int]]:
        rate = 48000
        edges = []
        for i in range(self.bands):
            lo = LOW_HZ * (HIGH_HZ / LOW_HZ) ** (i / self.bands)
            hi = LOW_HZ * (HIGH_HZ / LOW_HZ) ** ((i + 1) / self.bands)
            k_lo = max(1, int(lo / rate * FFT_SIZE))
            k_hi = max(k_lo + 1, int(hi / rate * FFT_SIZE))
            edges.append((k_lo, k_hi))
        return edges

    # ------------------------------------------------------------------ run
    def open(self, device_index: int | None = None) -> bool:
        if not self.available():
            self.error = "缺少 numpy 或 pyaudiowpatch"
            return False
        try:
            self._pa = pyaudio.PyAudio()
            if device_index is None:
                dev = self._pa.get_default_wasapi_loopback()
            else:
                dev = self._pa.get_device_info_by_index(int(device_index))
            rate = int(dev["defaultSampleRate"])
            channels = int(dev["maxInputChannels"])
            self.device_name = str(dev["name"])
            self.device_index = int(dev["index"])
            self._rate = rate
            self._channels = channels
            self._stream = self._pa.open(
                format=pyaudio.paFloat32, channels=channels, rate=rate,
                input=True, input_device_index=self.device_index,
                frames_per_buffer=FFT_SIZE,
            )
            self._buffer = np.zeros(FFT_SIZE, dtype=np.float32)
            self.active = True
            self.error = None
            self._bands_for_rate(rate)
            return True
        except Exception as exc:  # noqa: BLE001
            self.error = f"音频设备打开失败: {exc}"
            self.active = False
            self._close_resources()
            return False

    def _bands_for_rate(self, rate: int) -> None:
        edges = []
        for i in range(self.bands):
            lo = LOW_HZ * (HIGH_HZ / LOW_HZ) ** (i / self.bands)
            hi = LOW_HZ * (HIGH_HZ / LOW_HZ) ** ((i + 1) / self.bands)
            k_lo = max(1, int(lo / rate * FFT_SIZE))
            k_hi = max(k_lo + 1, int(hi / rate * FFT_SIZE))
            edges.append((k_lo, k_hi))
        self._edges = edges

    def run(self) -> None:
        if not self.active:
            return
        window = np.hanning(FFT_SIZE)
        while not self._stop_event.is_set():
            try:
                raw = self._stream.read(FFT_SIZE, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.float32)
                if self._channels > 1:
                    samples = samples.reshape(-1, self._channels).mean(axis=1)
                if samples.size < FFT_SIZE:
                    samples = np.pad(samples, (0, FFT_SIZE - samples.size))
                self._buffer = samples[:FFT_SIZE]
                mono = self._buffer * window
                spectrum = np.abs(np.fft.rfft(mono)) / (FFT_SIZE / 2)
                rms = float(np.sqrt(np.mean(self._buffer ** 2)))
                bass_slice = spectrum[max(1, int(45 / self._rate * FFT_SIZE)):
                                      max(2, int(220 / self._rate * FFT_SIZE) + 1)]
                bass = float(np.sqrt(np.sum(bass_slice ** 2)))
                flux = float(np.sqrt(np.sum(np.maximum(0, spectrum - self._previous_spectrum) ** 2))) if self._previous_spectrum is not None else 0.0
                self._previous_spectrum = spectrum
                levels = []
                for k_lo, k_hi in self._edges:
                    seg = spectrum[k_lo:k_hi]
                    mag = float(seg.max()) if seg.size else 0.0
                    db = 20 * math.log10(mag + 1e-7)
                    level = (db + 62.0) / 62.0
                    levels.append(max(0.0, min(1.0, level)))
                with self._lock:
                    self.rms = rms
                    self._rhythm.update(rms * self.gain, bass * self.gain, flux * self.gain,
                                        FFT_SIZE / self._rate)
                    self._last_update = time.perf_counter()
                    prev = self.levels
                    smoothed = []
                    for old, new in zip(prev, levels):
                        new = min(1.0, new * self.gain)
                        smoothed.append(new if new > old else old * 0.55 + new * 0.45)
                    self.levels = smoothed
            except Exception as exc:  # noqa: BLE001
                if not self._stop_event.is_set():
                    self.error = f"音频读取失败: {exc}"
                self.active = False
                break

    def snapshot(self) -> list[float]:
        return self.reactive_snapshot()["levels"]

    def reactive_snapshot(self) -> dict:
        with self._lock:
            age = max(0.0, time.perf_counter() - self._last_update) if self._last_update is not None else 100.0
            return {"levels": [v * math.exp(-max(0, age - .10) / .10) for v in self.levels],
                    "pulse": self._rhythm.pulse * math.exp(-age / .13),
                    "energy": self._rhythm.energy * math.exp(-age / .10),
                    "beat_count": self._rhythm.beat_count}

    def stop(self) -> None:
        self._stop_event.set()
        # Read blocks for one FFT buffer (~43ms). Do not close underneath read().
        if self.ident is not None and self is not threading.current_thread():
            self.join(timeout=2)
            if self.is_alive():
                raise RuntimeError("音频采集线程仍在退出")
        self._close_resources()
        self.active = False

    def _close_resources(self) -> None:
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pa:
                self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        self.active = False
        self._stream, self._pa = None, None
