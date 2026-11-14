# Front-end brief: Lab Kee Zubaan

For the person refining the page (`static/`). The backend and its API are stable, so the page can be redesigned freely as long as the rules at the end are respected. Pull first (`git pull --rebase`), commit small, never force-push.

## Who uses it
A patient or a family caregiver, very often on a **phone**, often older, often not at ease with medical words or with typing. Many speak Urdu. They arrive worried. The page must feel calm, simple and trustworthy.

## The one idea
Add a report, then see it in simple words, listen to it, and ask questions. Nothing else should compete for attention.

## Flow (two screens only)
1. **Start**: one big drop zone (PDF, .txt, .md) and one button, "Explain my report". Two quiet text links under it: "Paste the text instead" and "Try an example".
2. **Results** (the start screen is hidden, a "Add a different report" link is at the top). Order, top to bottom:
   1. Urgent banner (only when something is urgent).
   2. **In short** card with the Listen button (the hero of the page).
   3. "I need a little more information" (only when age or sex is missing). Age and sex fields, one Update button.
   4. **Your results**: one card per test, colour coded.
   5. **Questions to ask your doctor** (3 to 5).
   6. **Ask about your report**: chat with a large microphone button.
   7. Disclaimer, then Share on WhatsApp and Print.

Rules for choices: the only global choice is the language (English, Urdu, Roman Urdu) in the header. No other settings, menus or toggles. A new option needs a strong reason.

## Look and feel
- Palette (Sapphire, Ocean, Jade; light background): sapphire `#0042AC` primary, ocean `#00D3FB` accent, jade `#83FD80` for "good", ink `#0B1F3A`, page `#F4F8FF`. Status colours: normal green, low and high amber, urgent red, unsure grey. Never rely on colour alone: every status has a word chip.
- Type: system font stack for English (fast, nothing to download). Urdu uses **Noto Nastaliq Urdu** (in `static/fonts`), right to left, line height about 2.25 (Nastaliq needs tall lines). Base size 18px.
- Shape: large rounded cards, generous spacing, one primary button per screen.
- Motion: only meaningful motion (sound bars on Listen, a pulse on the microphone, a small spinner). Respect `prefers-reduced-motion`.
- The sound-bars motif (from the logo) is the visual signature: keep it on Listen.

## Responsive rules (phone first)
- Design at **375 px** wide first, then 768 px (tablet) and 1280 px. No horizontal scroll at any width (check `document.documentElement.scrollWidth <= innerWidth`).
- Tap targets at least 44 px. Text at least 16 px. Inputs 16 px or more so iPhones do not zoom.
- The language control becomes full width on phones. The In-short card stacks (text above, Listen below, full width).
- Test on a real phone, in portrait and landscape, with the keyboard open in the chat.

## Accessibility
Skip link, visible focus rings, labels on every control, `aria-live` for status and chat, `role="alert"` on the urgent banner, enough contrast (4.5:1), works with the keyboard only, works with browser zoom 200 percent.

## Voice behaviour (do not change the logic, restyle freely)
- The summary audio is requested as soon as results appear, so Listen starts at once.
- Chat answers asked by voice are answered by voice (device voice if it has the language, otherwise the server voice).
- The first tap on the page unlocks audio on phones.
- If a voice cannot play, say so in plain words. Never stay silent.

## Urdu and Roman Urdu
- Language change must not lose the report: the page calls `POST /api/explain` with `use_ai:false` (instant) and then with AI.
- Urdu text elements get class `rtl` (right to left plus Nastaliq). Numbers and English test names inside Urdu text stay readable.
- Roman Urdu is plain left-to-right Latin text.

## API the page uses
`POST /api/analyze` (`use_ai:false` first), `POST /api/analyze-file`, `POST /api/explain`, `POST /api/chat`, `POST /api/stt`, `GET /api/tts-stream`, `GET /api/warmup`, `GET /api/demo-reports`. Shapes are in the README.

## Hard rules
1. **Never** put model or server text into the page as HTML (`textContent` only). A test fails if `innerHTML` appears.
2. No external scripts, fonts or CDNs (the venue Wi-Fi may be bad, and nothing should leave the page).
3. No mention of any event, competition or template in the page.
4. Do not show names or record numbers anywhere (the server removes them for the AI, keep it that way on screen too).
5. Keep the empty, loading, error and urgent states for every screen.

## Checklist before saying "done"
- [ ] 375, 768 and 1280 px, portrait and landscape, no horizontal scroll
- [ ] English, Urdu and Roman Urdu with a real report (try samples P004, P011, P012, P013)
- [ ] Urgent report shows the banner and speaks the warning first
- [ ] Missing age or sex asks, and answering updates the results
- [ ] Upload a PDF, a .txt and pasted text
- [ ] Listen, microphone and typed question all work on a phone
- [ ] Keyboard only, and with a screen reader if possible
- [ ] `pytest` passes and `python scripts/smoke_test.py` passes
