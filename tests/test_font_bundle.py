"""Source assets survive migration; the sole Function excludes every binary."""
import json
import unittest
from pathlib import Path
class FontBundleTests(unittest.TestCase):
    def test_single_function_excludes_binary_assets(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/"vercel.json").read_text())
        self.assertEqual(list(config["functions"]),["api/index.py"])
        self.assertEqual(list((root/"api").glob("*.py")),[root/"api/index.py"])
        excludes=config["functions"]["api/index.py"]["excludeFiles"]
        self.assertIn("assets/fonts/**",excludes)
        self.assertIn("assets/reference-library/**/*.jpeg",excludes)
        self.assertTrue(all(r["destination"]=="/api/index.py" for r in config["rewrites"]))
        manifest=json.loads((root/"assets/blob-manifest.json").read_text())
        self.assertEqual(len(manifest["fonts"]),6)
        for e in manifest["fonts"]:
            self.assertTrue((root/e["license"]).is_file())
            self.assertTrue((root/e["source"]).is_file())
