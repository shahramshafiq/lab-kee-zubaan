"""The 3D welcome and background are decoration: they must be local, safe, small, and never trap the user."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "static"
client = TestClient(app)


def read(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_new_files_exist_and_scene_is_small():
    for name in ("intro.js", "intro.css", "night.css", "scene.js"):
        assert (STATIC / name).exists(), name
    assert (STATIC / "scene.js").stat().st_size < 700_000  # the built 3D scene, about 535 KB (133 KB compressed)


def test_no_unsafe_html_or_outside_urls_in_the_new_scripts():
    for name in ("intro.js", "app.js"):
        js = read(name)
        assert not re.search(r"innerHTML|insertAdjacentHTML|document\.write|eval\(", js), name
    for name in ("intro.js", "intro.css", "night.css", "index.html"):
        assert not re.search(r"""(src|href|url\()\s*=?\s*["']?https?://""", read(name)), name


def test_welcome_can_never_trap_the_user():
    html = read("index.html")
    assert "intro-on" in html and "setTimeout" in html  # the page opens itself even if the welcome code fails
    assert 'id="enter"' in html and "prefers-reduced-motion" in html
    assert "intro-reduced" in read("intro.css") and "prefers-reduced-motion" in read("night.css")
    js = read("intro.js")
    assert "4200" in js  # opens by itself after a few seconds
    # the welcome shows on every visit (the user asked for this), also with reduced motion (as a soft fade)
    assert "sessionStorage" not in html and "sessionStorage" not in js
    assert "intro-reduced" in html and "intro-reduced" in read("intro.css")


def test_light_cards_on_the_dark_page_set_their_own_dark_text():
    """The page text is light (dark theme). Any white card must say what its text colour is, or it becomes unreadable."""
    css = read("night.css")
    assert re.search(r"\.result\s*\{[^}]*color:\s*#0b1f3a", css), ".result card text colour"
    assert re.search(r"\.chat\s*\{[^}]*color:\s*#0b1f3a", css), ".chat card text colour"
    assert re.search(r"\.needs\s*\{[^}]*color:", css), ".needs card text colour"


def test_page_does_not_mention_any_event():
    blob = " ".join(read(n).lower() for n in ("index.html", "intro.js", "intro.css", "night.css", "app.js", "style.css"))
    assert "hackathon" not in blob and "tech fusion" not in blob and "techfusion" not in blob


def test_scripts_are_served_with_the_right_type_and_compressed():
    r = client.get("/static/scene.js", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers.get("content-encoding") == "gzip"


def test_the_api_is_never_compressed_so_streaming_stays_fast():
    r = client.get("/api/health", headers={"accept-encoding": "gzip"})
    assert "content-encoding" not in r.headers


def test_font_is_served():
    r = client.get("/static/fonts/noto-nastaliq-urdu-arabic-400.woff2")
    assert r.status_code == 200 and r.content[:4] == b"wOF2"
