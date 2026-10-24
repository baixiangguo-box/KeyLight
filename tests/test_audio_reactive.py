"""Deterministic audio response tests; no output playback or input device."""
import math
import unittest
from unittest.mock import patch

from kbdrv.audio import AudioAnalyzer, RhythmTracker, FFT_SIZE, np
from kbdrv.effects import render


class AudioReactiveTests(unittest.TestCase):
    def test_silence_and_noise_do_not_create_beats(self):
        tracker = RhythmTracker()
        for _ in range(100):
            tracker.update(.0005, .0003, .001, .04)
        self.assertEqual((tracker.pulse, tracker.energy, tracker.beat_count), (0,0,0))

    def test_each_beat_attacks_then_decays(self):
        tracker = RhythmTracker()
        for beat in range(6):
            tracker.update(.08, .06, .08, .04)
            self.assertGreater(tracker.pulse, .9)
            self.assertEqual(tracker.beat_count, beat + 1)
            for _ in range(11):
                tracker.update(0, 0, 0, .04)
            self.assertLess(tracker.pulse, .04)
        self.assertLess(tracker.energy, .02)

    def test_steady_tone_has_no_periodic_fake_flashes(self):
        tracker = RhythmTracker()
        for _ in range(150):
            tracker.update(.06, .04, 0, .04)
        self.assertEqual(tracker.beat_count, 1)
        self.assertLess(tracker.pulse, .0001)
        self.assertGreater(tracker.energy, .5)

    def test_spectral_attack_detects_treble_without_bass(self):
        tracker = RhythmTracker()
        for _ in range(20):
            tracker.update(.025, 0, 0, .04)
        before = tracker.beat_count
        tracker.update(.025, 0, .04, .04)
        self.assertEqual(tracker.beat_count, before + 1)
        self.assertGreater(tracker.pulse, .9)

    def test_stalled_capture_fades_instead_of_freezing(self):
        audio = AudioAnalyzer()
        audio.levels = [1.] * 22
        audio._last_update = 10
        audio._rhythm.pulse = audio._rhythm.energy = 1
        with patch('kbdrv.audio.time.perf_counter', return_value=11):
            snap = audio.reactive_snapshot()
        self.assertLess(snap['pulse'], .001)
        self.assertLess(snap['energy'], .001)
        self.assertLess(max(snap['levels']), .001)

    def test_checkerboard_alternates_neighbors_and_preserves_brightness(self):
        options = dict(color=(255,0,0), color2=(0,0,255), levels=[0]*22,
                       audio_energy=0, rows=5, row_offset=1)
        idle = render('audio', 0, audio_pulse=0, **options)
        self.assertEqual(set(idle), {(0,0,0)})
        bright = render('audio', 0, audio_pulse=1, audio_beat=0, **options)
        self.assertEqual(sum(max(c) > 40 for c in bright[22:]), 55)
        self.assertEqual(bright[22], (107,0,0))
        self.assertLess(max(bright[23]), 5)
        swapped = render('audio', 0, audio_pulse=1, audio_beat=1, **options)
        self.assertLess(max(swapped[22]), 5)
        self.assertGreater(max(swapped[23]), 60)
        dim = render('audio', 0, audio_pulse=1, brightness=.5, **options)
        self.assertTrue(all(max(b) <= max(a)/2 for a,b in zip(bright,dim)))
        self.assertEqual(bright, render('audio', 999, audio_pulse=1, **options))

    def test_separate_bands_drive_different_cells(self):
        levels = [0.] * 22
        levels[0] = 1
        frame = render('audio', 0, color=(255,255,255), color2=(255,255,255),
                       levels=levels, audio_pulse=0, audio_energy=0, rows=5, row_offset=1)
        self.assertGreater(max(frame[22]), 120)
        self.assertEqual(max(frame[24]), 0)
        levels[0], levels[10] = 0, 1
        moved = render('audio', 0, color=(255,255,255), color2=(255,255,255),
                       levels=levels, audio_pulse=0, audio_energy=0, rows=5, row_offset=1)
        self.assertEqual(max(moved[22]), 0)
        self.assertGreater(max(moved[24]), 120)

    def test_radial_mode_moves_center_and_fades_with_distance(self):
        options = dict(color=(255,255,255), color2=(255,255,255), levels=[0]*22,
                       audio_energy=0, audio_style='radial', rows=5, row_offset=1)
        frame = render('audio', 0, audio_pulse=1, audio_center=(11,2), **options)
        center = 3*22+11
        self.assertGreater(frame[center][0], frame[center+1][0])
        self.assertGreater(frame[center+1][0], frame[center+3][0])
        self.assertGreater(frame[center+3][0], frame[center+8][0])
        self.assertEqual(frame[center-3], frame[center+3])
        self.assertEqual(frame[center-22], frame[center+22])
        moved = render('audio', 0, audio_pulse=1, audio_center=(3,2), **options)
        self.assertGreater(moved[3*22+3][0], moved[center][0])
        silent = render('audio', 0, audio_pulse=0, audio_center=(3,2), **options)
        self.assertEqual(set(silent), {(0,0,0)})

    @unittest.skipIf(np is None, 'numpy unavailable')
    def test_pcm_fft_pipeline_detects_repeated_kicks(self):
        rate = 48000
        samples = np.arange(rate*3) / rate
        phase = samples % .5
        wave = .12 * np.sin(2 * math.pi * 75 * samples) * np.exp(-phase*28)
        wave[phase > .18] = 0
        audio = AudioAnalyzer()
        audio.active, audio._rate, audio._channels = True, rate, 2
        audio._bands_for_rate(rate)
        chunks = [np.repeat(wave[i:i+FFT_SIZE,None], 2, axis=1).astype(np.float32).tobytes()
                  for i in range(0, len(wave)-FFT_SIZE+1, FFT_SIZE)]
        class Stream:
            def read(self, *args, **kwargs):
                data = chunks.pop(0)
                if not chunks:
                    audio._stop_event.set()
                return data
        audio._stream = Stream()
        audio.run()
        self.assertGreaterEqual(audio._rhythm.beat_count, 6)
        self.assertLessEqual(audio._rhythm.beat_count, 7)
        self.assertLess(audio._rhythm.pulse, .1)
