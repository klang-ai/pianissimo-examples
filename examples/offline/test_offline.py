"""Tests for the parts that need no model, no network and no ffmpeg.

    python3 examples/offline/test_offline.py

Stdlib unittest only, so it runs in a plain interpreter without the venv.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ask  # noqa: E402
import clip  # noqa: E402
import fetch  # noqa: E402
import summary  # noqa: E402


def word(i, text, step=0.35, length=0.3):
    return {"word": text, "start": i * step, "end": i * step + length}


def words(sentence):
    return [word(i, w) for i, w in enumerate(sentence.split())]


class Fetch(unittest.TestCase):
    def test_seconds_reads_both_duration_forms(self):
        self.assertEqual(fetch.seconds("1:02:03"), 3723)
        self.assertEqual(fetch.seconds("12:30"), 750)
        self.assertEqual(fetch.seconds("62"), 62)
        self.assertIsNone(fetch.seconds(""))
        self.assertIsNone(fetch.seconds(None))

    def test_similarity_is_word_overlap_over_the_shorter_title(self):
        self.assertEqual(fetch.similarity("Sommar i P1: Zlatan", "Zlatan Ibrahimović: Sommar i P1"), 1.0)
        self.assertEqual(fetch.similarity("A", "B"), 0.0)
        self.assertEqual(fetch.similarity("", ""), 0.0)
        self.assertAlmostEqual(fetch.similarity("Ekot lördagsintervju", "Ekots lördagsintervju 20 sep"), 0.5)

    def test_normal_keeps_swedish_letters_whole(self):
        self.assertEqual(fetch.normal("Lördagsintervju på Åland"), "lördagsintervju på åland")

    def test_normal_strips_punctuation_and_entities(self):
        self.assertEqual(fetch.normal("Sommar &amp; vinter, i P1!"), "sommar vinter i p1")

    def test_spotify_and_ytdlp_are_off_by_default(self):
        self.assertFalse(fetch.ANY_LINK)
        with self.assertRaises(fetch.NotFound) as cm:
            fetch.resolve("https://open.spotify.com/episode/7t5EYXfU6usMYduhVBS9nQ")
        self.assertIn("--any-link", str(cm.exception))
        self.assertIsNone(fetch.from_ytdlp("https://www.youtube.com/watch?v=x"))


class Summary(unittest.TestCase):
    def test_normal_keeps_letters_and_digits_only(self):
        self.assertEqual(summary._normal("Hej, DÄR! Vad… sa du 2?"), "hej där vad sa du 2")

    def test_stamp_counts_minutes_past_the_hour(self):
        self.assertEqual(summary.stamp(3725), "62:05")
        self.assertEqual(summary.stamp(0), "00:00")

    def test_outline_skips_chapters_without_a_title(self):
        job = {"title": "Ep", "show": "Show",
               "chapters": [{"start": 0, "title": "A", "gist": "a"}, {"start": 30, "title": "", "gist": "x"}]}
        self.assertEqual(summary.outline("A", job), "Avsnitt A: Ep (Show)\n[A 00:00] A: a")


class Ask(unittest.TestCase):
    pieces = [(0, "Vi pratar om skatten och skatterna i Sverige"),
              (30, "Fotboll och VM i sommar"),
              (60, "Skattesystemet är krångligt sa hon")]

    def test_stems_drop_stop_words_and_cut_at_five_letters(self):
        self.assertEqual(ask._stems("Skatterna är höga, sa Anna-Karin"), ["skatt", "höga", "anna", "karin"])

    def test_search_finds_inflected_forms_in_episode_order(self):
        self.assertEqual(ask.search(self.pieces, "vad sa de om skatt?"), [0, 2])

    def test_search_best_first_when_not_ordered(self):
        hits = ask.search(self.pieces, "skattesystemet krångligt", ordered=False)
        self.assertEqual(hits[0], 2)

    def test_search_returns_nothing_for_unrelated_or_empty_questions(self):
        self.assertEqual(ask.search(self.pieces, "bilar"), [])
        self.assertEqual(ask.search(self.pieces, "och det är"), [])
        self.assertEqual(ask.search([], "skatt"), [])

    def test_excerpt_formats_with_stamp(self):
        self.assertEqual(ask.excerpt(self.pieces, [1], summary.stamp), "[00:30] Fotboll och VM i sommar")


class Clip(unittest.TestCase):
    sentence = "Det här är en ganska lång mening som fortsätter. Sedan en till."

    def test_cues_break_on_width_sentence_end_and_pause(self):
        groups = clip.cues(words(self.sentence))
        self.assertEqual([" ".join(w["word"] for w in g) for g in groups],
                         ["Det här är en ganska lång mening", "som fortsätter.", "Sedan en till."])
        paused = words("ett två tre fyra")
        paused[2]["start"] += 2.0
        paused[2]["end"] += 2.0
        paused[3]["start"] += 2.0
        paused[3]["end"] += 2.0
        self.assertEqual(len(clip.cues(paused)), 2)

    def test_wrap_balances_two_lines_with_a_karaoke_tag_per_word(self):
        ws = clip.cues(words(self.sentence))[0]
        out = clip._wrap(ws)
        self.assertEqual(out.count("\\N"), 1)
        self.assertEqual(out.count("{\\kf"), len(ws))
        self.assertNotIn("{", clip._wrap([word(0, "a{b}c")]).replace("{\\kf", ""))

    def test_span_lines_the_quote_up_and_tolerates_drift(self):
        ws = words(self.sentence)
        self.assertEqual(clip.span(ws, "ganska lång mening"), (4, 6))
        self.assertEqual(clip.span(ws, "ganska långa meningen som"), (4, 7))
        self.assertEqual(clip.span(ws, None), (0, len(ws) - 1))
        with self.assertRaises(LookupError):
            clip.span(ws, "helt annan text här")

    def test_locate_prefers_the_whole_quote_over_its_opening_words(self):
        # The opening words occur at 0 s as well; the full quote only at 60 s. A
        # window is two pieces, so the one that starts at 30 s is the first to hold it.
        job = {"seconds": 90.0, "pieces": [
            (0, "vi pratar om skatten och skatterna i sverige idag"),
            (30, "annat"),
            (60, "vi pratar om skatten och skatterna i sverige imorgon igen")]}
        self.assertEqual(clip.locate(job, "vi pratar om skatten och skatterna i sverige imorgon igen"), (30, 90.0))
        self.assertEqual(clip.locate(job, "skatterna i sverige idag"), (0, 60.0))
        self.assertEqual(clip.locate(job, start=70), (70.0, 90.0))
        with self.assertRaises(LookupError):
            clip.locate(job, "finns inte")

    def test_locate_spans_a_piece_boundary(self):
        job = {"seconds": 60.0, "pieces": [(0, "slutet av ett stycke"), (30, "början på nästa")]}
        self.assertEqual(clip.locate(job, "ett stycke början på"), (0, 60.0))

    def test_ass_time_and_drawtext_escape(self):
        self.assertEqual(clip._ass_time(3661.234), "1:01:01.23")
        self.assertEqual(clip._ass_time(-1), "0:00:00.00")
        self.assertEqual(clip._drawtext_escape("Ekot: 50% 'ja', x"), "Ekot\\: 50\\% ’ja’\\, x")

    def test_ass_has_one_dialogue_line_per_cue(self):
        ws = words(self.sentence)
        out = clip.ass(ws, 0.0)
        self.assertEqual(out.count("Dialogue:"), len(clip.cues(ws)))
        self.assertIn(f"PlayResX: {clip.W}", out)


class Download(unittest.TestCase):
    def test_ytdlp_item_is_refused_without_the_flag(self):
        # An item can come straight from the page or from a saved archive job,
        # so download() checks the flag itself.
        with self.assertRaises(fetch.NotFound) as cm:
            fetch.download({"kind": "ytdlp", "audio": "https://example.com/x"}, "/tmp", lambda d, t: None)
        self.assertIn("--any-link", str(cm.exception))

    def test_ytdlp_is_killed_at_the_deadline_even_when_silent(self):
        import subprocess
        import tempfile
        real_popen, real_deadline, real_flag = subprocess.Popen, fetch.YTDLP_DEADLINE, fetch.ANY_LINK

        def silent(args, **kw):
            # Holds stdout open and prints nothing, like a stalled download.
            return real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kw)
        try:
            fetch.ANY_LINK, fetch.YTDLP_DEADLINE = True, 1
            fetch.subprocess.Popen = silent
            with tempfile.TemporaryDirectory() as d, self.assertRaises(fetch.NotFound) as cm:
                fetch.download({"kind": "ytdlp", "audio": "x"}, d, lambda a, b: None)
            self.assertIn("did not finish", str(cm.exception))
        finally:
            fetch.subprocess.Popen, fetch.YTDLP_DEADLINE, fetch.ANY_LINK = real_popen, real_deadline, real_flag


class Archive(unittest.TestCase):
    def test_an_add_while_the_worker_is_leaving_is_picked_up(self):
        import tempfile
        import threading
        import types
        sys.modules.setdefault("asr", types.SimpleNamespace(RATE=16000))
        import archive

        with tempfile.TemporaryDirectory() as root:
            archive.ROOT = root
            a = archive.Archive(engine=None)
            processed, gate, left = [], threading.Event(), threading.Event()
            a._process = lambda ep: (processed.append(ep["id"]), ep.update(status="done"))

            real_next = a._next

            def slow_next():
                ep = real_next()
                if ep is None and not gate.is_set():
                    # The worker has seen an empty queue and is about to leave.
                    gate.set()
                    left.wait(2)
                return ep
            a._next = slow_next

            a.add([{"audio": "https://example.com/1.mp3"}])
            gate.wait(2)
            # Added in the window between the empty check and the thread exiting.
            a.add([{"audio": "https://example.com/2.mp3"}])
            left.set()
            for _ in range(50):
                if len(processed) == 2:
                    break
                threading.Event().wait(0.05)
            self.assertEqual(len(processed), 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
