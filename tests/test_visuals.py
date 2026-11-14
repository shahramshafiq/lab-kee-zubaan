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
    for name in ("intro.js", "intro.css", "theme.css", "scene.js"):
        assert (STATIC / name).exists(), name
    assert (STATIC / "scene.js").stat().st_size < 700_000  # the built 3D scene, about 535 KB (133 KB compressed)


def test_no_unsafe_html_or_outside_urls_in_the_new_scripts():
    for name in ("intro.js", "app.js"):
        js = read(name)
        assert not re.search(r"innerHTML|insertAdjacentHTML|document\.write|eval\(", js), name
    for name in ("intro.js", "intro.css", "theme.css", "index.html"):
        assert not re.search(r"""(src|href|url\()\s*=?\s*["']?https?://""", read(name)), name


def test_welcome_can_never_trap_the_user():
    html = read("index.html")
    assert "intro-on" in html and "setTimeout" in html  # the page opens itself even if the welcome code fails
    assert 'id="enter"' in html and "prefers-reduced-motion" in html
    assert "intro-reduced" in read("intro.css") and "prefers-reduced-motion" in read("theme.css")
    js = read("intro.js")
    assert "4200" in js  # opens by itself after a few seconds
    # the welcome shows on every visit (the user asked for this), also with reduced motion (as a soft fade)
    assert "sessionStorage" not in html and "sessionStorage" not in js
    assert "intro-reduced" in html and "intro-reduced" in read("intro.css")


def test_cards_set_their_own_text_colour_in_every_theme():
    """The page text can be light (ink, night). Cards must say their own text colour (a token), or they become unreadable."""
    css = read("theme.css")
    for card in (".result", ".chat"):
        assert re.search(re.escape(card) + r"\s*\{[^}]*color:\s*var\(--card-ink\)", css), card + " card text colour"
    assert re.search(r"\.needs\s*\{[^}]*color:", css), ".needs card text colour"
    for theme in ("ivory", "ink", "night"):
        assert theme in css
    # the 3D scene takes its colours from the theme, so it matches whichever theme is chosen
    assert "--scene-a" in css and "--scene-a" in (Path(__file__).resolve().parent.parent / "tools" / "scene.src.js").read_text(encoding="utf-8")
    assert 'href="/static/theme.css"' in read("index.html")
    assert '"ivory"' in read("index.html")  # ivory is the page theme


def test_page_does_not_mention_any_event():
    blob = " ".join(read(n).lower() for n in ("index.html", "intro.js", "intro.css", "theme.css", "app.js", "style.css"))
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
