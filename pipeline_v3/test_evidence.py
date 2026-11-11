"""Tests for archive integrity and refusing to reuse a completed run directory."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from evidence import verify


class ArchiveIntegrity(unittest.TestCase):
    def fixture(self,root):
        (root/'trace.csv').write_text('measured\n1\n')
        (root/'sources').mkdir();(root/'sources'/'model.py').write_text('x=1\n')
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        source=sha(root/'sources'/'model.py')
        inventory={str(p.relative_to(root)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in root.rglob('*') if p.is_file()}
        (root/'manifest.json').write_text(json.dumps(dict(status='complete',source_sha256={'model.py':source},artifacts=inventory)))

    def test_intact_and_mutated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);self.assertEqual(verify(root),2)
            (root/'trace.csv').write_text('changed\n1\n')
            with self.assertRaises(ValueError):verify(root)

    def test_missing_and_unlisted(self):
        for kind in ('missing','extra'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root)
                if kind=='missing':(root/'trace.csv').unlink()
                else:(root/'stale.csv').write_text('stale')
                with self.assertRaises(ValueError):verify(root)

    def test_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):verify(Path(tmp))

    def test_existing_directory_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=subprocess.run([sys.executable,str(Path(__file__).with_name('study.py')),'--validate-only','--output',str(root)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('Output directory already exists',result.stderr)
            after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)


if __name__=='__main__':unittest.main()
