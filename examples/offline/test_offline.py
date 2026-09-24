"""Tests for the parts that need no model, no network and no ffmpeg.

    python3 examples/offline/test_offline.py

Stdlib unittest only, so it runs in a plain interpreter without the venv.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import clip  # noqa: E402
import fetch  # noqa: E402


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

    def test_spotify_is_refused_with_a_way_forward(self):
        with self.assertRaises(fetch.NotFound) as cm:
            fetch.resolve("https://open.spotify.com/episode/7t5EYXfU6usMYduhVBS9nQ")
        self.assertIn("Apple Podcasts link or RSS feed", str(cm.exception))

    def test_a_direct_audio_link_needs_no_request(self):
        items = fetch.resolve("https://example.com/show/episode-12.mp3")
        self.assertEqual(items[0]["audio"], "https://example.com/show/episode-12.mp3")
        self.assertEqual(items[0]["via"], "a direct link")


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


if __name__ == "__main__":
    unittest.main(verbosity=1)
