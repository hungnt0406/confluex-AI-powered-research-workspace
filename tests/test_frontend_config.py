from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_next_turbopack_root_is_pinned_to_frontend() -> None:
    config = (ROOT / "frontend" / "next.config.mjs").read_text()

    assert 'fileURLToPath(import.meta.url)' in config
    assert 'const __dirname = path.dirname' in config
    assert 'root: __dirname' in config
    assert 'root: path.dirname(__dirname)' not in config
