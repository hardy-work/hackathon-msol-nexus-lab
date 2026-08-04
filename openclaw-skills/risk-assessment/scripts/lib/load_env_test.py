import tempfile
import unittest
from pathlib import Path

from load_env import load_env


class LoadEnvTest(unittest.TestCase):
    def test_parses_key_value_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text("# comment\nFOO=bar\nBAZ=./qux.json\n\n", encoding="utf-8")
            env = load_env(p)
            self.assertEqual(env, {"FOO": "bar", "BAZ": "./qux.json"})

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(load_env(Path("/nonexistent/.env")), {})


if __name__ == "__main__":
    unittest.main()
