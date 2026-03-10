# Mini-Agent Setup

Repository default runtime id:
- `mini-agent`

## 1) Install

Install `mini-agent` in the same Python environment used for this repo.

```bash
pip install mini-agent
which mini-agent
mini-agent --version
```

If the binary lands in `~/.local/bin`, add it to your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## 2) Non-Billing Health Check

Run the unified setup checker:

```bash
python verify_agent_setup.py --agent mini-agent
```

This uses `mini-agent --version`, so it does not send a model request and does not consume credits.

## 3) Recommended Evaluation Run

```bash
python clear_evaluation_system.py --agent mini-agent --refresh-capability-profile
python clear_evaluation_system.py --agent mini-agent
```

Mode notes:
- `--refresh-capability-profile`: probe then evaluate.
- `--probe-agent`: same as refresh.
- `--probe-only`: probe only.

## 4) Troubleshooting

- `mini-agent: command not found`
  - fix PATH or reinstall in the active Python environment.
- capability/profile looks stale
  - rerun `--refresh-capability-profile`.
- phase3 tool traces look incomplete
  - inspect the latest task JSON and confirm parser evidence was captured from stdout/detailed logs.

## 5) Security

- never commit keys or local runtime config,
- rotate credentials immediately if leaked.
