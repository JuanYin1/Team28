# Step 1: config the mini-agent system 
在miniagent的readme： 
https://github.com/MiniMax-AI/Mini-Agent

# Step2: run tests:
## Phase 1 - Initial Assessment (Basic Evaluation)
```python
  python agentic_sys/integrated_mini_agent_evaluation.py
```
  What it does:
  - Runs 5 basic test cases (arithmetic, logic, file ops, debugging, system analysis)
  - No memory monitoring - only functional testing
  - Generates results in phase1/ folder
  - Creates comprehensive_analysis_YYYYMMDD_HHMMSS.md report

## Phase 2 - Enhanced Memory Investigation
```
  python agentic_sys/enhanced_comprehensive_evaluation.py
```
  
## What it does:
  - Runs 12 reasoning-enhanced test cases with real-time monitoring
  - Captures memory, CPU, disk, network metrics
  - Detects resource bottlenecks and confidence scores
  - Generates results in phase2/ folder (as enhanced_* files)
  - Creates enhanced analysis report with bottleneck identification