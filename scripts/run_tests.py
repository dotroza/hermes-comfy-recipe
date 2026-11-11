"""Run tests with a disposable Hermes profile and fail-closed detached-process boundary."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='comfy-recipe-tests-') as tmp:
        home = Path(tmp)
        os.environ['HERMES_HOME'] = str(home / 'hermes')
        os.environ['TMPDIR'] = str(home)
        tempfile.tempdir = str(home)
        from plugin import core, installer
        core.DATA = home / 'hermes' / 'plugin-data' / 'comfy-recipe'
        core.STATE = core.DATA / 'instances.json'
        original = installer._detached

        def isolated_detached(args, out_path, cwd):
            if not Path(cwd).resolve().is_relative_to(home.resolve()):
                raise AssertionError(f'Test tried to spawn a worker outside its sandbox: {cwd}')
            return original(args, out_path, cwd)

        try:
            with patch.object(installer, '_detached', side_effect=isolated_detached):
                suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
                result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            tempfile.tempdir = None


if __name__ == '__main__':
    raise SystemExit(main())
