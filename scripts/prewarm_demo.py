"""Warms the app for a recording and shows what each demo question answers.

    python scripts/prewarm_demo.py [base_url] [folder with the demo files]

For each demo file and language it analyses the file, asks the AI for the explanation, asks the demo questions through the
same streaming route the microphone uses, and fetches the audio of every spoken sentence. After this the answers and the
voice are cached, so a recording shows instant, repeatable answers. It also prints the answer and the time to the first
sentence, which doubles as a check that the answers are right.
"""
import json
import sys
import time
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
FOLDER = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "demo"

QUESTIONS = {
    "Demo1_Ayesha_Khan_Report.pdf": {
        "en": ["What does my hemoglobin result mean?", "Is my TSH normal?", "What does a low platelet count mean?",
               "What does SGPT mean?", "Do I have diabetes?", "Show me another patient's report"],
        "ur": ["میرا ہیموگلوبن کیا بتاتا ہے؟", "کیا میرا ٹی ایس ایچ نارمل ہے؟"],
        "roman_urdu": ["Mera hemoglobin kya batata hai?", "Kya mera TSH normal hai?"],
    },
    "Demo2_Photo_Report.jpg": {
        "en": ["Is my fasting sugar normal?", "What does my cholesterol result mean?"],
        "ur": ["کیا میری شوگر نارمل ہے؟"],
    },
}
client = httpx.Client(timeout=120)


def speak(text, language):
    t = time.perf_counter()
    r = client.get(BASE + "/api/tts-stream", params={"language": language, "text": text})
    return time.perf_counter() - t, r.status_code


def main():
    for filename, by_language in QUESTIONS.items():
        raw = (FOLDER / filename).read_bytes()
        for language, questions in by_language.items():
            r = client.post(BASE + "/api/analyze-file", files={"file": (filename, raw)},
                            params={"language": language, "use_ai": "false"})
            if r.status_code != 200:
                print("FAILED to read", filename, r.text)
                continue
            data = r.json()
            sid = data["session_id"]
            if data["summary"]["needs"]:  # the photo has no sex line: answer the question the page would ask
                client.post(BASE + "/api/chat", json={"session_id": sid, "message": "I am male", "language": language})
            ex = client.post(BASE + "/api/explain", json={"session_id": sid, "language": language, "use_ai": True}).json()["explanation"]
            seconds, status = speak(ex["voice"], language)
            print(f"\n=== {filename} | {language} | summary voice audio {seconds:.1f}s ({status})")
            print("   summary:", ex["summary"][:200].replace("\n", " "))
            for q in questions:
                started = time.perf_counter()
                first, spoken = None, []
                with client.stream("POST", BASE + "/api/chat-stream",
                                   json={"session_id": sid, "message": q, "language": language, "voice": True}) as resp:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        ev = json.loads(line)
                        if ev["type"] in ("sentence", "final") and first is None:
                            first = time.perf_counter() - started
                        if ev["type"] == "sentence":
                            spoken.append(ev["spoken"])
                        elif ev["type"] == "final":
                            spoken = [ev.get("spoken") or ev["answer"]]
                            answer = ev["answer"]
                if spoken and "answer" not in locals():
                    answer = " ".join(spoken)
                answer = " ".join(spoken) if spoken and not any(True for _ in []) else answer
                audio = [speak(t, language)[0] for t in spoken]
                print(f"Q: {q}\n   first text {first or 0:.2f}s | audio {', '.join(f'{a:.1f}s' for a in audio)}\n   A: {answer[:300]}")


if __name__ == "__main__":
    main()
