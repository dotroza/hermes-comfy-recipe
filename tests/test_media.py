"""comfy_media: real ffmpeg round-trips on a synthetic clip (skipped when ffmpeg is absent)."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from plugin import media

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not on PATH")
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.src = cls.dir / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=60:duration=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe(self):
        i = media.probe(self.src)
        self.assertEqual((i["width"], i["height"], i["fps"]), (1080, 1920, 60.0))
        self.assertEqual(i["frames"], 600)
        self.assertTrue(i["has_audio"])

    def test_convert_trim_resize_fps_next_to_source(self):
        r = media.convert(str(self.src), duration=3.042, width=544, height=960, fps=24)
        o = r["output"]
        self.assertEqual(Path(o["path"]).parent, self.dir)
        self.assertEqual(Path(o["path"]).name, "clip_544x960_24fps_0-3.042s.mp4")
        self.assertEqual((o["width"], o["height"], o["fps"], o["frames"]), (544, 960, 24.0, 73))
        self.assertTrue(o["has_audio"])

    def test_convert_fit_pads_and_refuses_overwrite(self):
        o = media.convert(str(self.src), width=960, height=544, mode="fit", duration=1)["output"]
        self.assertEqual((o["width"], o["height"]), (960, 544))
        with self.assertRaises(ValueError):
            media.convert(str(self.src), fps=24, out=str(self.src))
        with self.assertRaises(ValueError):
            media.convert(str(self.src))

    def test_first_last_index_and_time_frames(self):
        r = media.frames(str(self.src), ["first", "last", 120, "t=5"])
        names = [Path(o["path"]).name for o in r["outputs"]]
        self.assertEqual(names, ["clip_first.png", "clip_last.png", "clip_f120.png", "clip_t5s.png"])
        for o in r["outputs"]:
            self.assertGreater(Path(o["path"]).stat().st_size, 1000)
        with self.assertRaises(ValueError):
            media.frames(str(self.src), [600])

    def test_split_then_join(self):
        parts = media.split(str(self.src), 4, out_dir=str(self.dir / "segs"))["outputs"]
        self.assertEqual(len(parts), 3)
        self.assertAlmostEqual(sum(p["duration_s"] for p in parts), 10, delta=0.2)
        j = media.join([p["path"] for p in parts], out=str(self.dir / "rejoined.mp4"))["output"]
        self.assertAlmostEqual(j["duration_s"], 10, delta=0.2)
        self.assertEqual((j["width"], j["height"]), (1080, 1920))
        self.assertTrue(j["has_audio"])

    def test_chained_split_shares_one_frame_and_join_drops_it(self):
        parts = media.split(str(self.src), 3, out_dir=str(self.dir / "chain"), chained=True,
                            width=544, height=960, fps=24)["outputs"]
        self.assertEqual(len(parts), 4)
        self.assertEqual([p["frames"] for p in parts[:3]], [73, 73, 73])  # 3 s + the shared frame
        self.assertEqual((parts[0]["width"], parts[0]["height"], parts[0]["fps"]), (544, 960, 24.0))
        j = media.join([p["path"] for p in parts], out=str(self.dir / "chain_joined.mp4"), drop_first=1)
        self.assertEqual(j["drop_first"], 1)
        self.assertEqual(j["output"]["frames"], sum(p["frames"] for p in parts) - (len(parts) - 1))
        self.assertAlmostEqual(j["output"]["duration_s"], 10, delta=0.15)
        self.assertTrue(j["output"]["has_audio"])

    def test_sheet(self):
        r = media.sheet(str(self.src), count=8, columns=4)
        self.assertTrue(Path(r["path"]).is_file())

    def test_copy_to_input_reuses_identical_and_never_overwrites(self):
        inp = self.dir / "input"
        a = media.copy_to_input(self.src, inp)
        self.assertFalse(a["reused"])
        self.assertTrue(media.copy_to_input(self.src, inp)["reused"])
        other = self.dir / "other" / "clip.mp4"
        other.parent.mkdir()
        other.write_bytes(b"different")
        b = media.copy_to_input(other, inp)
        self.assertEqual(b["input_name"], "clip_1.mp4")
        self.assertEqual((inp / "clip.mp4").read_bytes(), self.src.read_bytes())

    def test_handle_to_input(self):
        inp = self.dir / "input2"
        r = media.handle({"action": "frames", "path": str(self.src), "which": ["first"], "to_input": True},
                         input_dir_for=lambda name: inp)
        self.assertEqual(r["input_files"][0]["input_name"], "clip_first.png")
        self.assertIn("close + open", r["next"])


if __name__ == "__main__":
    unittest.main()
