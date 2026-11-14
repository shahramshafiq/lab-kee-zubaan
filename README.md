# Lab Kee Zubaan

**Lab reports in plain words, safe by design.** Built for the Tech Fusion '26 AI Hackathon, Challenge B (Medical Lab Report Explainer).

A patient or a family caregiver opens a lab report and gets: each result marked normal, low, high or urgent; a simple explanation of what every test measures; 3 to 5 questions to ask the doctor; and a short spoken summary they can listen to. They can then ask questions about the report by typing or by voice.

## Why it is different from pasting a report into a chatbot

1. **Code decides the facts, the AI only writes the words.** A rules engine reads the lab's own files and classifies every value. The same report always gives the same answer.
2. **The AI is checked.** Any explanation that contains a number that is not in the facts, or sounds like a diagnosis, is thrown away and a plain rules-based text is shown instead. So the app still works when the AI is slow, down or wrong.
3. **Privacy is built in.** Name and record number are removed before anything is sent to the AI. A conversation is locked to one report and refuses questions about other patients.
4. **It never guesses.** Missing age or sex: it asks. Unknown test or unit: "cannot be classified from the files". Every decision shows which file and line it came from.
5. **Voice for people who do not want to read.** Short spoken summary, speech to text for questions, spoken answers, in English or Urdu.

## Run it

With Docker (one command):

```bash
cp .env.example .env     # then put your own keys in .env (the app also runs without keys, with rules text only)
docker compose up --build
```

Open http://localhost:8000

Without Docker (Python 3.10 or newer):

```bash
python -m venv .venv
.venv\Scripts\activate            # on Mac or Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # then edit .env
uvicorn app.main:app --port 8000
```

Run the tests (they never call a real AI service):

```bash
pytest
```

## How it works

```
report text -> clean filler -> extract demographics and results -> normalise names and units
            -> rules engine (ranges by age and sex, urgent limits, edge rules)   <- the lab's reference files
            -> remove name and record number
            -> AI writes plain words (English, Urdu, Roman Urdu) -> checker (numbers, no diagnosis)
            -> page: cards, doctor questions, spoken summary, locked chat
```

| Part | File |
|---|---|
| Reads the lab's reference files, remembers file and line | `app/knowledge.py` |
| Cleans a report and reads results in many layouts | `app/extract.py` |
| Unit conversions, shown as a formula | `app/units.py` |
| Statuses and the doctor questions | `app/engine.py` |
| Only code that calls an AI service: retries, fallback between providers, deadline | `app/llm.py` |
| Plain words plus the checker and a cache | `app/explain.py` |
| Chat locked to one report | `app/chat.py` |
| Question guardrails (other patients, diagnosis, medicine, attacks) | `app/guard.py` |
| Speech to text (Whisper) and text to speech | `app/voice.py` |
| Request ids, counters (`/api/metrics`), rate limit | `app/observability.py` |
| Routes | `app/main.py` |

### API

| Route | What it does |
|---|---|
| `POST /api/analyze` | `{report_id` or `report_text, language, age?, sex?, use_ai?}` gives results, explanation, doctor questions, `session_id` |
| `POST /api/analyze-file` | same, for an uploaded `.txt` or `.md` report |
| `POST /api/chat` | `{session_id, message, language, voice?}` gives an answer locked to that report |
| `POST /api/stt` | a recording gives text |
| `POST /api/tts` | text gives audio (mp3) |
| `GET /api/demo-reports`, `/api/health`, `/api/metrics` | samples, status, counters |

Result statuses: `normal`, `low`, `high`, `urgent`, `cannot_classify`, `needs_demographics`.

### Rules we follow (from the lab's own files)

- A value exactly on a range limit is **normal**. Age limits are inclusive.
- Missing age or sex: say the right range cannot be chosen and ask. Never guess from the name.
- No matching range, or a unit that cannot be converted: "cannot be classified from the files".
- Urgent values (hit or pass a dangerous limit) get a "see a doctor today" warning and questions first.
- Never say a patient has a disease. Only a licensed doctor can diagnose.
- Never discuss another patient.

## Robustness

Judged by tests, not by trust: about 100 automated tests cover all 14 lab reports, other ways of writing results, other units, every range edge, age edges, missing data, huge and garbage input, attacks hidden in a report, attacks in chat, and the AI being down or returning nonsense.

## Known failure cases and limits (we would rather say them than hide them)

- **Urgent limit wording.** The lab file says "hit or pass" but the table says "less than / greater than". We treat a value exactly on the limit as urgent (the safe side).
- **Missing sex for a test that does not need it.** The lab rule says ask when age or sex is missing, so we ask even for tests where one range fits everyone. Set `STRICT_DEMOGRAPHICS=false` to ask only when needed.
- **Unit conversion factors are standard textbook values** (for example glucose mmol/L x 18). The lab files do not list them.
- **Ranges only exist for ages 18 to 100.** Children get "cannot be classified" until the lab supplies ranges.
- **Tests with no range** (for example ferritin, kidney tests) are marked "cannot be classified", on purpose.
- **Only text and markdown reports.** PDFs and photos need text extraction or OCR (future work).
- **The alias list is small** (the lab glossary plus a few common spellings). An unknown spelling is marked unclassified, not guessed.
- **The AI chat answers are checked for invented numbers and diagnosis wording**, but not for every possible medical claim. Questions about diagnosis or medicine never reach the AI.
- **Free AI plans have limits.** When they are slow or busy we show the rules text, which is correct but plainer.
- **Voice.** Text to speech uses Microsoft's free neural voices through the `edge-tts` package (an unofficial service). If it fails, the page uses the browser's own voice. Roman Urdu is read with an English voice. Speech recognition of Urdu is good but not perfect, so the typed text is always shown.
- **Sessions live in memory.** A restart clears them. One instance only.

## Business idea in one paragraph

Patients cannot read their results and labs spend call-centre time explaining them, while critical values need fast action. Lab Kee Zubaan is meant to be offered by a lab or hospital: the report goes out with a plain-language, voice-ready explanation in the patient's language, urgent results go to a staff member first, and the lab's own reference ranges decide the facts. Later phases: WhatsApp delivery with a staff review step for urgent results, PDF reading, and a lab-desk queue for critical values.

## How this was built

AI coding assistants helped write and review parts of the code. All behaviour is covered by tests, and the team reviewed and ran the result.

## Layout

```
app/            backend code (see the table above)
static/         the web page (HTML, CSS, JavaScript, no external libraries)
lab_reports/    the lab's reference files and sample reports (from the organizers)
tests/          automated tests
Dockerfile, docker-compose.yml, .env.example
```
