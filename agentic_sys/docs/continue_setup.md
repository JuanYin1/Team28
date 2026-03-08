# Continue Setup (API Key Mode, Copy-Paste)

This guide is for teammates.
Use the provided workspace API key to run Continue without `cn login`.

Repository defaults:
- Workspace: `zhiruis-workspace-2`
- Model: `anthropic/claude-haiku-4-5`
- Config: `continuedev/default-cli-config`

## 0) Go to project folder

```bash
cd agentic_sys
```

## 1) Install Continue CLI

```bash
npm i -g @continuedev/cli
which cn
cn --version
```

If `cn` is not found, run:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## 2) Set API key (required)

Replace `<ORG_SCOPED_KEY>` with the key shared by the team.

```bash
export CONTINUE_API_KEY="<ORG_SCOPED_KEY>"
```

Persist it for future terminals:

```bash
echo 'export CONTINUE_API_KEY="<ORG_SCOPED_KEY>"' >> ~/.zshrc
source ~/.zshrc
```

## 3) Quick connectivity check

```bash
cn -p "Reply with exactly OK and nothing else." --auto
```

Expected output: `OK`

## 4) Project health check

```bash
python verify_continue_setup.py
```

Expected: `Success: True` and `Diagnosis: ok`.

## 5) Run evaluation scripts

```bash
python run_single_test.py --agent continue
python integrated_agent_evaluation.py --agent continue
python enhanced_comprehensive_evaluation.py --agent continue
python clear_evaluation_system.py --agent continue
```

## 6) Common errors and fixes

- `auth_or_model_not_configured`
  - `CONTINUE_API_KEY` is missing/invalid, or shell did not load it.
  - Fix: `echo $CONTINUE_API_KEY` and set it again.

- `account_credits_exhausted`
  - Workspace credits are out.
  - Fix: ask workspace admin to top up.

- `cn: command not found`
  - PATH issue.
  - Fix: add `~/.local/bin` to PATH and restart shell.

## 7) Security rules

- Do not commit API keys.
- Do not paste keys in issues/chat/screenshots.
- If leaked, revoke and rotate immediately.
