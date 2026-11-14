# Where to deploy

**Recommendation: ship Docker as the guaranteed delivery, and add a live link as a convenience for people who cannot run Docker.** The submission asks for a live link or Docker, so Docker alone is enough. A live link is nicer for a judge, and it also makes the voice faster (see below), but it needs care.

## Why Docker first
It starts with one command on any machine, `docker compose up --build`, and nothing depends on a free hosting service staying awake. It is tested from a clean image in this repo.

## Why a live link is still worth it
- A judge can try it in one click, on a phone.
- The server talks to the speech and AI services from a data centre, which is usually faster than from a home network. On the development laptop the voice service answers in about 2 to 4 seconds. A cloud host is likely to be quicker. (Measure it, do not assume.)
- HTTPS is needed for the microphone on phones, and every host below gives it.

## Hosts that fit this app
The app is a long-running Python server with in-memory sessions and calls that can take a few seconds. That rules out serverless hosts (Vercel, Netlify functions): short time limits, no shared memory between requests.

| Host | Fit | Watch out for |
|---|---|---|
| Hugging Face Spaces (Docker) | Good, free, HTTPS | Sleeps after inactivity, slow first request |
| Render (Docker web service) | Good, simple, free tier | Free service sleeps after inactivity, about a minute to wake |
| Railway or Fly.io | Good | Free credit may be limited |

Current free-tier rules change often. Check them before relying on one. If the evaluation might call the live link automatically, a sleeping service can time out, so keep it awake (a free uptime pinger on `/api/health` every few minutes) and test it first.

## Fastest path: Render blueprint (about 5 minutes)
`render.yaml` in the repo describes the service, so there is nothing to configure by hand.
1. Sign in at render.com with the GitHub account that owns the repo, and allow it to read the repo.
2. New + > Blueprint > choose `lab-kee-zubaan` > Apply.
3. When it asks for `GROQ_API_KEY` and `GEMINI_API_KEY`, paste your own keys (they stay in Render, not in git).
4. Wait for the first build (a few minutes). Open the `onrender.com` link it shows.
5. Check it: `python scripts/smoke_test.py --base https://YOUR-NAME.onrender.com --ai --voice`
6. Optional: a free uptime pinger on `https://YOUR-NAME.onrender.com/api/health` every 5 minutes keeps the free service awake.

The container was tested with a custom `PORT` (Render sets one) and reports healthy.

## Steps (any other Docker host)
1. Create a service from the GitHub repo (it detects the `Dockerfile`).
2. Set the environment variables in the host's dashboard, never in the repo: `GROQ_API_KEY`, `GEMINI_API_KEY`, `PROVIDER_ORDER=groq,gemini`. Optional: `LLM_MAX_CALLS_PER_HOUR` (default 1500), `RATE_ANALYZE_PER_MIN`, `RATE_CHAT_PER_MIN`.
3. Health check path: `/api/health`. The container listens on `$PORT` (default 8000).
4. Open the link and run: `python scripts/smoke_test.py --base https://YOUR-LINK --ai --voice`
5. Put the link in the submission form. Keep the Docker instructions in the README as well.

## Protecting the keys and the budget on a public link
- Keys only live in the host's environment. `.env` is never committed.
- Per-address rate limits and an hourly AI call budget are built in. When the budget is used up the app keeps working with its rules text.
- `/api/usage` shows calls, tokens and calls left this hour.
- If the free AI quota runs out, the app does not break: it answers with the rules text.

## Optional: a faster English voice
Groq has a fast text-to-speech model (about 0.3 s). It needs the account owner to accept the model's terms once in the Groq console. After that, set `TTS_ENGLISH_PROVIDER=groq`. If it is not accepted, the app silently keeps using the Edge voice.
