# CAL FIRE Alert System — Deployment Options Guide

**Purpose:** Help stakeholders choose how to run the San Diego fire monitoring and Teams alerting system.

**Project:** SDFireCoordinateProject  
**Data source:** [CAL FIRE public incident API](https://incidents.fire.ca.gov/) (same data as the public website; no browser automation)  
**Notifications:** Microsoft Power Automate → Teams channel **General** (adaptive cards)

---

## Executive summary

| What exists today | What still needs a decision |
|-------------------|---------------------------|
| Working Python monitor (`fire_check.py`) | **Where** it runs (laptop vs cloud) |
| Power Automate → Teams integration (tested) | **How often** it checks (default: every 5 minutes) |
| County filtering (default: San Diego) | Whether to add **AI** (usually not needed for alerts) |

**Bottom line:** The hard part (data + alerts) is done. The choice is **how to keep it running 24/7** with acceptable cost, reliability, and IT overhead.

---

## What the system does (all options share this core)

Every deployment option uses the same logical pipeline:

```mermaid
flowchart TB
    subgraph Data
        API["CAL FIRE GeoJSON API<br/>(free, public)"]
    end

    subgraph Processing["Python: fire_check.py"]
        Fetch["1. Fetch active incidents"]
        Filter["2. Filter by county<br/>(e.g. San Diego)"]
        Dedupe["3. Compare to seen_fires.json<br/>(avoid repeat alerts)"]
        Build["4. Build Teams adaptive card"]
    end

    subgraph Notify
        PA["Power Automate<br/>HTTP trigger"]
        Teams["Microsoft Teams<br/>#General channel"]
    end

    API --> Fetch --> Filter --> Dedupe --> Build --> PA --> Teams
```

### Behaviors that are the same in every option

| Behavior | Description |
|----------|-------------|
| **No website scraping** | Reads official JSON API — faster and more stable than automating a browser |
| **County filter** | Only alerts for counties listed in `MONITOR_COUNTIES` (default: `san diego`) |
| **New fires only** | `seen_fires.json` stores incident IDs already alerted |
| **Rich Teams cards** | Title + details (name, coordinates, acres, containment, Google Maps link) |
| **No CAL FIRE API key** | Public feed; no subscription cost |

### What is *not* included unless you choose a specific option

| Capability | Manual | Local agent | Cloud | AI agent |
|------------|:------:|:-----------:|:-----:|:--------:|
| Runs without human starting it | ❌ | ✅ | ✅ | ✅ |
| Runs when laptop is off | ❌ | ❌ | ✅ | ✅ |
| Natural-language Q&A | ❌ | ❌ | ❌ | ✅ |
| Extra monthly cost | $0 | $0 | $0–low | $$$ |

---

## Option 0 — Manual checks (current baseline)

**What it is:** Someone runs a command when they want to check. No background process.

```mermaid
sequenceDiagram
    participant User
    participant Script as fire_check.py
    participant API as CAL FIRE API
    participant PA as Power Automate
    participant Teams

    User->>Script: python3 fire_check.py
    Script->>API: GET incidents
    API-->>Script: JSON
    alt New fire in monitored county
        Script->>PA: POST adaptive card
        PA->>Teams: Message in General
    else No new fires
        Script-->>User: "No new fires found"
    end
    Note over Script: Process exits
```

### How to run

```bash
python3 fire_check.py          # check once, alert if new
python3 fire_check.py --test     # send one test card to Teams
```

### Pros

| Pro | Why it matters |
|-----|----------------|
| **Simplest** | No install, no cloud account, no scheduling |
| **Zero ongoing ops** | Nothing running in the background |
| **Easy to demo** | Good for proving the integration works |
| **Free** | No hosting costs |

### Cons

| Con | Why it matters |
|-----|----------------|
| **Not real-time monitoring** | Fires can appear between manual runs |
| **Human dependency** | Easy to forget to run |
| **Not suitable for operations** | Misses overnight / weekend incidents |

### Best for

- Proof of concept and stakeholder demos  
- Occasional manual checks  
- **Not** recommended for production alerting  

### Effort to deploy

| Item | Estimate |
|------|----------|
| Setup time | Already done |
| Ongoing maintenance | None |
| Technical skill | Run one terminal command |

---

## Option 1 — Local background agent (Mac / PC always on)

**What it is:** A loop runs `fire_check.py` every N minutes (default 5) on a computer that stays powered on.

```mermaid
flowchart TB
    subgraph Host["Computer (Mac or Windows)"]
        Agent["fire_agent.py<br/>infinite loop"]
        Check["fire_check.py"]
        Seen["seen_fires.json"]
        Env[".env secrets"]
    end

    Agent -->|"every 5 min"| Check
    Check --> Seen
    Check --> Env
    Check --> API["CAL FIRE API"]
    Check --> PA["Power Automate"]

    style Agent fill:#e8f4ea
```

### Two sub-options

#### 1A — Foreground agent (terminal open)

```bash
python3 fire_agent.py
```

- Stops when terminal closes or Mac sleeps (unless configured otherwise)

#### 1B — macOS LaunchAgent (recommended on Mac)

```bash
./install_agent.sh
```

- Starts at login, restarts if crash, logs to `agent.log`

```mermaid
flowchart LR
    Boot["Mac boots / user logs in"] --> LaunchD["macOS LaunchAgent"]
    LaunchD --> Agent["fire_agent.py"]
    Agent --> Loop["Check every 5 min"]
    Loop --> Agent
```

### Pros

| Pro | Why it matters |
|-----|----------------|
| **True 24/7 while machine is on** | Catches new fires within ~5 minutes |
| **Already built in repo** | `fire_agent.py` + `install_agent.sh` exist |
| **Free** | No cloud hosting bill |
| **Full control** | Logs on disk, easy to debug |
| **Uses existing Power Automate flow** | No change to Teams setup |

### Cons

| Con | Why it matters |
|-----|----------------|
| **Machine must stay on** | Laptop closed / asleep = no checks |
| **Power / network outages** | Gaps in coverage |
| **Single point of failure** | One computer, one operator |
| **Not ideal for teams** | Tied to one person's device unless moved to a server |

### Best for

- Individual or small team with a Mac Mini / always-on office PC  
- Low budget, quick path to production  
- UCSD / lab machine that stays powered  

### Effort to deploy

| Item | Estimate |
|------|----------|
| Setup time | 15–30 minutes |
| Ongoing maintenance | Occasional log checks; update `.env` if webhook rotates |
| Technical skill | Basic terminal; macOS `launchctl` for 1B |

### Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Mac sleeps | Energy settings: prevent sleep on power; use desktop/Mac Mini |
| Webhook URL leaked | Rotate in Power Automate; never commit `.env` |
| Disk fills with logs | Rotate `agent.log` periodically |

---

## Option 2 — Cloud-scheduled monitor (laptop independent)

**What it is:** The **same** `fire_check.py` logic runs on a schedule in the cloud. The cloud platform is the “timer”; you usually run **one check per invocation** (not an infinite loop).

```mermaid
flowchart TB
    subgraph Cloud["Cloud scheduler"]
        Cron["GitHub Actions cron<br/>OR Azure timer<br/>OR Logic App recurrence"]
    end

    subgraph Run["Each run (2–30 sec)"]
        Script["fire_check.py --once"]
    end

    Cron -->|"every 5 min"| Script
    Script --> API["CAL FIRE API"]
    Script --> PA["Power Automate"]
    PA --> Teams["Teams General"]

    style Cloud fill:#e8eef4
```

### Sub-options compared

#### 2A — GitHub Actions (recommended cloud starter)

```mermaid
sequenceDiagram
    participant GH as GitHub Actions
    participant Script as fire_check.py
    participant API as CAL FIRE
    participant PA as Power Automate

    Note over GH: Cron: */5 * * * *
    GH->>Script: Run in CI runner
    Script->>API: GET incidents
    Script->>PA: POST if new fire
```

| Pros | Cons |
|------|------|
| Free for public repos; generous free tier for private | Need GitHub repo + secrets setup |
| No server to manage | `seen_fires.json` must persist (commit artifact or use cache) |
| Runs when laptop is off | ~1–5 min schedule granularity (not millisecond-precise) |
| Good audit trail (workflow logs) | Requires basic CI familiarity |

**Typical cost:** $0/month (within free tier)

---

#### 2B — Microsoft Power Automate / Logic Apps only (no Python)

Rebuild the pipeline entirely in Power Automate: recurrence → HTTP GET CAL FIRE → parse JSON → condition → post Teams.

```mermaid
flowchart LR
    Recur["Recurrence<br/>every 5 min"] --> HTTP["HTTP GET<br/>CAL FIRE API"]
    HTTP --> Parse["Parse JSON"]
    Parse --> Filter["Filter county"]
    Filter --> Teams["Post to Teams"]
```

| Pros | Cons |
|------|------|
| Stays in Microsoft 365 ecosystem | **Re-implement** deduplication logic in flow |
| No Python hosting | Complex JSON parsing in low-code designer |
| Uses existing Teams connection | Harder to version-control and test |
| | Flow run limits on license tier |

**Typical cost:** $0 if included in existing M365; check Premium connector limits

---

#### 2C — Azure Function / small VPS

Run Python on Azure Functions (timer trigger) or a $5–6/mo Linux VPS with `cron` + `fire_agent.py --once`.

| Pros | Cons |
|------|------|
| Most control, production-grade | Higher setup complexity |
| Persistent storage for `seen_fires.json` easy | May incur monthly cost (VPS or Azure) |
| Custom intervals | Needs someone comfortable with Azure/Linux |

**Typical cost:** $0–15/month

---

### Option 2 — Overall pros & cons

### Pros

| Pro | Why it matters |
|-----|----------------|
| **Works when staff laptops are off** | Reliable for operations |
| **Team-visible** | Not tied to one person's Mac |
| **Same alert quality** | Still uses Power Automate → Teams |
| **Scales to many counties** | Just config change |

### Cons

| Con | Why it matters |
|-----|----------------|
| **More setup than Option 1** | Secrets, CI, or Azure knowledge |
| **`seen_fires.json` in cloud** | Must persist state between runs (artifact/cache/DB) |
| **Secrets management** | Webhook URL in GitHub Secrets / Key Vault |
| **Slight delay possible** | Cron jitter (e.g. 5–7 min between checks) |

### Best for

- Production alerting for a team or organization  
- Stakeholders who need reliability without a dedicated machine  
- UCSD / departmental use where a Mac cannot stay on 24/7  

### Effort to deploy

| Sub-option | Setup time | Skill level |
|------------|------------|-------------|
| GitHub Actions | 1–2 hours | GitHub + YAML basics |
| Power Automate only | 2–4 hours | Power Automate intermediate |
| Azure / VPS | 4–8 hours | Cloud or Linux admin |

---

## Option 3 — AI agent (LLM-driven)

**What it is:** A large language model (ChatGPT, Cursor Agent, Copilot, etc.) orchestrates tools — including optionally calling the fire monitor — and can answer questions in natural language.

```mermaid
flowchart TB
    User["User: Is there a fire near UCSD?"] --> LLM["AI Agent / LLM"]
    LLM --> Tool1["Tool: query CAL FIRE API"]
    LLM --> Tool2["Tool: run fire_check.py"]
    LLM --> Tool3["Tool: geocode address"]
    LLM --> Reason["Reason + summarize"]
    Reason --> Out["Natural language answer<br/>+ optional alert"]

    Tool1 --> API["CAL FIRE API"]
    Tool2 --> PA["Power Automate"]
```

### Example capabilities AI could add

- “Summarize all active fires in Southern California.”  
- “Is this incident within 20 miles of our facility?”  
- “What changed since yesterday?”  
- Draft incident reports for leadership  

### Pros

| Pro | Why it matters |
|-----|----------------|
| **Flexible questions** | Not limited to fixed alert rules |
| **Rich explanations** | Good for executives and public comms drafts |
| **Can combine sources** | Weather, maps, news (if tools added) |

### Cons

| Con | Why it matters |
|-----|----------------|
| **Overkill for simple alerts** | “Notify me on new fire” does not need AI |
| **Ongoing API cost** | Per-token charges |
| **Non-deterministic** | Can hallucinate; not ideal for life-safety alone |
| **More engineering** | Tools, guardrails, monitoring, evals |
| **Compliance / review** | May need human approval for operational messages |

### Best for

- Research, situational awareness dashboards, Q&A interfaces  
- **Not** recommended as the **only** alerting path for emergencies  

### Recommended architecture if AI is desired later

```mermaid
flowchart LR
    subgraph Reliable["Layer 1 — Keep this (required)"]
        Monitor["fire_check.py<br/>scheduled"]
        Monitor --> Teams["Teams alerts"]
    end

    subgraph Optional["Layer 2 — Add later"]
        AI["AI assistant"]
        AI -.->|"reads same API"| API["CAL FIRE"]
        AI -.->|"does not replace"| Monitor
    end
```

**Rule:** Use **Option 1 or 2** for alerts; add **Option 3** only as a separate assistant on top.

### Effort to deploy

| Item | Estimate |
|------|----------|
| MVP assistant | 1–2 weeks |
| Production-grade (guardrails, evals) | 1–3 months |
| Typical monthly cost | $20–200+ depending on usage |

---

## Side-by-side decision matrix

### Reliability & operations

| Criterion | Option 0 Manual | Option 1 Local agent | Option 2 Cloud | Option 3 AI |
|-----------|:---------------:|:--------------------:|:--------------:|:-----------:|
| 24/7 monitoring | ❌ | ⚠️ (if machine on) | ✅ | ⚠️ (depends on host) |
| Works laptop closed | ❌ | ❌ | ✅ | ✅ |
| Alert latency ~5 min | ❌ | ✅ | ✅ | N/A |
| Deterministic / testable | ✅ | ✅ | ✅ | ⚠️ |
| Ops complexity | Low | Low–Med | Med | High |

### Cost (typical)

| Option | Software | Hosting | People time |
|--------|----------|---------|-------------|
| 0 Manual | $0 | $0 | Low |
| 1 Local agent | $0 | $0 (existing PC) | Low |
| 2A GitHub Actions | $0 | $0 | Medium setup |
| 2B Power Automate only | $0* | $0 | Medium–High setup |
| 2C Azure / VPS | $0 | $0–15/mo | High setup |
| 3 AI agent | $20–200+/mo | Varies | High |

\*Assumes existing Microsoft 365 / Power Automate licensing.

### Security & compliance

| Topic | All options |
|-------|-------------|
| **Secrets** | `POWER_AUTOMATE_WEBHOOK_URL` must stay private (like a password) |
| **Data** | Public CAL FIRE data only; no PII in feed |
| **Teams** | Uses org Microsoft 365; aligns with existing UCSD identity (`nkasibatla@ucsd.edu`) |
| **Audit** | Cloud options (GitHub/Azure) provide run logs; local uses `agent.log` |

---

## High-level architecture comparison (one diagram)

```mermaid
flowchart TB
    subgraph O0["Option 0 — Manual"]
        U0[Human runs script] --> S0[fire_check.py]
    end

    subgraph O1["Option 1 — Local agent"]
        A1[fire_agent.py loop] --> S1[fire_check.py]
        M1[Mac / PC always on]
        M1 --- A1
    end

    subgraph O2["Option 2 — Cloud"]
        C2[Scheduler] --> S2[fire_check.py once per tick]
        C2 -.-> GH[GitHub Actions]
        C2 -.-> AZ[Azure / Logic App]
    end

    subgraph O3["Option 3 — AI"]
        LLM[LLM Agent] --> Tools[Tools/APIs]
        Tools --> S3[Optional: fire_check.py]
    end

    S0 --> API[CAL FIRE API]
    S1 --> API
    S2 --> API
    S3 --> API

    API --> PA[Power Automate]
    PA --> Teams[Teams General]
```

---

## What is already built (inventory)

| Component | Status | Role |
|-----------|--------|------|
| `fire_check.py` | ✅ Working | Core: fetch, filter, dedupe, notify |
| `fire_agent.py` | ✅ Working | Local scheduler loop |
| `install_agent.sh` | ✅ Ready | macOS auto-start |
| Power Automate → Teams | ✅ Tested | Notifications to General |
| `.env` configuration | ✅ Working | Counties, webhook, interval |
| `seen_fires.json` | ✅ Working | Dedup memory |
| GitHub Actions workflow | ❌ Not yet | Would enable Option 2A |
| AI / LLM layer | ❌ Not yet | Option 3 only |

---

## Recommendations by stakeholder priority

```mermaid
quadrantChart
    title Decision guide (complexity vs reliability)
    x-axis Low setup complexity --> High setup complexity
    y-axis Low reliability --> High reliability
    quadrant-1 Quick win
    quadrant-2 Production
    quadrant-3 Demo only
    quadrant-4 Over-engineered
    Option 0 Manual: [0.15, 0.2]
    Option 1 Local agent: [0.35, 0.65]
    Option 2 Cloud: [0.65, 0.9]
    Option 3 AI: [0.85, 0.5]
```

| If the priority is… | Recommended option |
|---------------------|-------------------|
| **Fastest path to 24/7 alerts this week** | **Option 1B** — `./install_agent.sh` on an always-on Mac |
| **Team reliability, laptop-independent** | **Option 2A** — GitHub Actions |
| **Stay 100% inside Microsoft 365** | **Option 2B** — Power Automate-only flow |
| **Demo / pilot only** | **Option 0** — manual runs |
| **Chatbot / “ask about fires”** | **Option 3** — only after Option 1 or 2 is live |

### Suggested phased rollout

```mermaid
gantt
    title Phased rollout (example)
    dateFormat YYYY-MM-DD
    section Phase 1
    Option 1 local agent (Mac)     :a1, 2026-05-16, 3d
    section Phase 2
    Option 2 cloud (GitHub Actions) :a2, after a1, 7d
    section Phase 3 (optional)
    AI Q&A assistant               :a3, after a2, 30d
```

1. **Week 1:** Option 1 — prove 24/7 alerts on one always-on machine.  
2. **Week 2–3:** Option 2 — migrate to cloud if Mac reliability is insufficient.  
3. **Later (optional):** Option 3 — AI layer for analysis, not primary alerting.

---

## Decision checklist (for the meeting)

Use this checklist when presenting to decision-makers:

- [ ] **Who must receive alerts?** (Individuals vs team channel — today: Teams General)
- [ ] **Must alerts work overnight and weekends?** (If yes → reject Option 0)
- [ ] **Is there an always-on computer?** (If yes → Option 1 is attractive)
- [ ] **If no always-on computer →** Option 2 required
- [ ] **Acceptable alert delay?** (Default 5 minutes is configurable)
- [ ] **Budget for hosting / AI?** ($0 vs $5–15/mo vs AI API costs)
- [ ] **Who maintains it?** (Name a primary + backup owner)
- [ ] **Need natural-language Q&A?** (If no → skip Option 3)
- [ ] **Regulatory / audit requirements?** (Favor Option 2 with logged runs)

---

## Quick reference — commands by option

| Option | How to run |
|--------|------------|
| **0 Manual** | `python3 fire_check.py` |
| **1A Foreground agent** | `python3 fire_agent.py` |
| **1B macOS background** | `./install_agent.sh` |
| **2 Cloud** | Not yet in repo — requires GitHub Actions / Azure setup |
| **3 AI** | Not in repo — separate project |

**Test Teams integration (any option):**

```bash
python3 fire_check.py --test
```

---

## Glossary

| Term | Meaning |
|------|---------|
| **Agent (this project)** | A program that runs repeatedly without human intervention — not necessarily artificial intelligence |
| **AI agent** | Software using an LLM to plan steps and use tools |
| **Dedupe** | `seen_fires.json` prevents alerting twice on the same incident |
| **GeoJSON** | JSON format for geographic data returned by CAL FIRE |
| **Power Automate** | Microsoft workflow that receives HTTP POST and posts to Teams |
| **Adaptive card** | Rich message format required by the Teams webhook flow |

---

## Document info

| Field | Value |
|-------|-------|
| Version | 1.0 |
| Date | May 16, 2026 |
| Repository | SDFireCoordinateProject |
| Contact | Project owner / primary maintainer |

---

*For setup instructions, see [README.md](../README.md).*
