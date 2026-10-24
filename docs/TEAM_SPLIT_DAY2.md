# Day 2 team split and git commands (same roles as Day 1)

**The rule:** every file changed or added on Day 2 belongs to **exactly one** person, so the five pushes never conflict. **Push in this order:** Tarun → Monish → Devaki → Member 4 → Member 5.

| # | Member (Day 1 role) | Day 2 work they own | Files |
|---|---|---|---|
| 1 | **Tarun (Loop)** | Act-and-verify loop wired into the agent, reviewer, trust checks, LLM key/model routing, control-room UI | `agent.py` `llm.py` `prompts/` `ui_server.py` `ui/` `run_ui.sh` `README.md` `team-form.md` `.gitignore` |
| 2 | **Monish (Host)** | Stack config, pre-flight, one-command runners, fault injection (23 incidents), mentor blind test, detection matrix | `config.py` `check_stack.py` `demo.sh` `run_day1.sh` `run_everything.sh` `practice/` |
| 3 | **Devaki (Tools)** | Baselines and deviation ranking, SLOW_TAIL, dependency health, error signatures, recovery verification | `tools.py` `verify.py` `llm_test.py` |
| 4 | **Member 4 (Output)** | Action allowlist and safety gates, schema, report, 31 offline tests, three-ideas proof, action log | `actions.py` `schema.json` `report.py` `tests/` `prove_three_ideas.py` `action_log.jsonl` |
| 5 | **Member 5 (Evidence)** | Sweeps, calibration, evaluation note, all docs and diagrams, every report | `run_all.py` `calibration.py` `evaluation-note.md` `docs/` `reports/` |

## 0. Tarun first: make the zip (excludes keys, `.venv`, `.git`, caches and fault state)

```bash
cd "/Users/taruns/Downloads/hakathon bosch " && zip -rq TEAM33-day2.zip "TEAM---33" -x "TEAM---33/.git/*" "TEAM---33/.venv/*" "TEAM---33/.env*" "*/__pycache__/*" "*.DS_Store" "TEAM---33/practice/.faultctl_state.json" "TEAM---33/practice/.mentor_secret.json" "TEAM---33/KILL_SWITCH" && ls -lh TEAM33-day2.zip
```

Share `TEAM33-day2.zip`. Each member unzips it and sets `ZIP` to the unzipped `TEAM---33` folder.

## 1. Tarun (Loop): push first

```bash
[ -d team33 ] || git clone https://github.com/1Monish8/TEAM---33.git team33
cd team33 && git pull --rebase origin main
git config user.name "Tarun"
git config user.email "taruns0648@gmail.com"
ZIP="PATH_TO_UNZIPPED_FOLDER"
cp "$ZIP/.gitignore" "$ZIP/README.md" "$ZIP/team-form.md" .
cp "$ZIP/agent.py" "$ZIP/llm.py" "$ZIP/ui_server.py" "$ZIP/run_ui.sh" .
cp -R "$ZIP/prompts" "$ZIP/ui" .
git add .gitignore README.md team-form.md agent.py llm.py ui_server.py run_ui.sh prompts/ ui/
git commit -m "Day 2 loop: dry run, human approval, act, verify, roll back; reviewer and trust checks; LLM key and model routing; control-room UI"
git pull --rebase origin main
git push origin main
```

## 2. Monish (Host)

```bash
[ -d team33 ] || git clone https://github.com/1Monish8/TEAM---33.git team33
cd team33 && git pull --rebase origin main
git config user.name "Monish"
git config user.email "YOUR_GITHUB_EMAIL"
ZIP="PATH_TO_UNZIPPED_FOLDER"
cp "$ZIP/config.py" "$ZIP/check_stack.py" "$ZIP/demo.sh" "$ZIP/run_day1.sh" "$ZIP/run_everything.sh" .
cp -R "$ZIP/practice" .
rm -f practice/.faultctl_state.json practice/.mentor_secret.json
git add config.py check_stack.py demo.sh run_day1.sh run_everything.sh practice/
git commit -m "Pre-flight check, one-command runners, 23 practice incidents (application + infrastructure), mentor blind test, fault detection matrix"
git pull --rebase origin main
git push origin main
```

## 3. Devaki (Tools)

```bash
[ -d team33 ] || git clone https://github.com/1Monish8/TEAM---33.git team33
cd team33 && git pull --rebase origin main
git config user.name "Devaki"
git config user.email "YOUR_GITHUB_EMAIL"
ZIP="PATH_TO_UNZIPPED_FOLDER"
cp "$ZIP/tools.py" "$ZIP/verify.py" .
cp "$ZIP/llm_test.py" . 2>/dev/null || true
git add tools.py verify.py
git add llm_test.py 2>/dev/null || true
git commit -m "Baselines and deviation ranking, SLOW_TAIL, dependency health (Kafka, Postgres, cache, disk), error signatures, recovery verification"
git pull --rebase origin main
git push origin main
```

## 4. Member 4 (Output)

```bash
[ -d team33 ] || git clone https://github.com/1Monish8/TEAM---33.git team33
cd team33 && git pull --rebase origin main
git config user.name "YOUR NAME"
git config user.email "YOUR_GITHUB_EMAIL"
ZIP="PATH_TO_UNZIPPED_FOLDER"
cp "$ZIP/actions.py" "$ZIP/schema.json" "$ZIP/report.py" "$ZIP/prove_three_ideas.py" "$ZIP/action_log.jsonl" .
cp -R "$ZIP/tests" .
git add actions.py schema.json report.py prove_three_ideas.py action_log.jsonl tests/
git commit -m "Action allowlist and safety gates (approval, kill switch, protected containers), extended schema and report, 31 offline tests, three-ideas proof"
git pull --rebase origin main
git push origin main
```

## 5. Member 5 (Evidence): push last

```bash
[ -d team33 ] || git clone https://github.com/1Monish8/TEAM---33.git team33
cd team33 && git pull --rebase origin main
git config user.name "YOUR NAME"
git config user.email "YOUR_GITHUB_EMAIL"
ZIP="PATH_TO_UNZIPPED_FOLDER"
cp "$ZIP/run_all.py" "$ZIP/calibration.py" "$ZIP/evaluation-note.md" .
cp -R "$ZIP/docs" "$ZIP/reports" .
find docs reports -name .DS_Store -delete
git add run_all.py calibration.py evaluation-note.md docs/ reports/
git commit -m "Sweeps and calibration, evaluation note, Day 2 report, architecture and data-flow diagrams, presentation script, live run evidence"
git pull --rebase origin main
git push origin main
```

## 6. After the last push (anyone)

```bash
cd team33 && git pull origin main && git log --format='%an' | sort -u && git log -p | grep -c "gsk_"
```

- **Expected:** all five names, and a key count of `0`.
- Then make sure the pushed repo matches the zip: `diff -rq --exclude=.git . "$ZIP"` should list only `.env*`, `.venv`, `__pycache__` and the fault-state files.
