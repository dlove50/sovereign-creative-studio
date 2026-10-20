import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import local_launcher as launcher


class FrontendBuildTests(unittest.TestCase):
    def test_build_validation(self):
        for stale, corrupt in [(False, False), (True, False), (False, True)]:
            with self.subTest(stale=stale, corrupt=corrupt), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                dist = root / ".next"
                chunks = dist / "static" / "chunks"
                chunks.mkdir(parents=True)
                (root / "src").mkdir()
                source = root / "src" / "page.tsx"
                source.write_text("export default function Page() {}")
                (dist / "BUILD_ID").write_text("test")
                (dist / "routes-manifest.json").write_text('{"destination":"http://127.0.0.1:8002"}')
                (chunks / "8698-test.js").write_text(
                    "self.webpackChunk_N_E.push([[5731],{}])" if corrupt
                    else "self.webpackChunk_N_E.push([[8698],{}])"
                )
                os.utime(source, (1, 1) if not stale else (4102444800, 4102444800))
                with patch.object(launcher, "FRONTEND", root), patch.dict(os.environ, {"NEXT_DIST_DIR": ".next"}), patch.object(launcher, "port_open", return_value=True), patch.object(launcher, "evict_port") as stop, patch.object(launcher.subprocess, "run", return_value=Mock(returncode=0)) as build:
                    launcher.ensure_frontend_build()
                    self.assertEqual(build.call_count, int(stale or corrupt))
                    self.assertEqual(stop.call_count, int(stale or corrupt))
                    if build.called:
                        self.assertEqual(build.call_args.kwargs["env"]["NEXT_DIST_DIR"], ".next")


if __name__ == "__main__":
    unittest.main()
