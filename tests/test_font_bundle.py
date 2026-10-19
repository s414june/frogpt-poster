"""Verify deployment ignore rules select exactly the renderer's font registry."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from gpt_package.font_registry import FONT_FAMILIES


class FontBundleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'git required to evaluate ignore rules')
    def test_bundle_contains_only_registered_fonts_and_licenses(self):
        repo = Path(__file__).resolve().parents[1]
        actual = sorted(p.relative_to(repo).as_posix() for p in (repo/'assets/fonts').rglob('*')
                        if p.is_file() and p.suffix.lower() in ('.ttf', '.otf', '.ttc'))
        expected = {'assets/fonts/'+p for group in FONT_FAMILIES.values() for p in group}
        licenses = {'assets/fonts/'+p.split('/')[0]+'/OFL.txt' for group in FONT_FAMILIES.values() for p in group}
        paths = actual + sorted(licenses)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git','init','-q',tmp],check=True)
            Path(tmp,'.gitignore').write_text((repo/'.vercelignore').read_text())
            for name in paths:
                p=Path(tmp,name);p.parent.mkdir(parents=True,exist_ok=True);p.touch()
            result=subprocess.run(['git','-C',tmp,'check-ignore','--no-index','--stdin'],
                input='\n'.join(paths)+'\n',text=True,capture_output=True)
            self.assertIn(result.returncode,(0,1))
            included=set(paths)-set(result.stdout.splitlines())
        self.assertEqual(included,expected|licenses)
        total=sum((repo/p).stat().st_size for p in expected)
        self.assertLess(total,80_000_000,'Fonts alone must leave runtime headroom under the deployment limit')
