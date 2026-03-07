#!/usr/bin/env python3
"""
Mini-Agent Comprehensive Evaluation System with CLEAR Framework
==============================================================
Implements Multi-Dimensional CLEAR Framework specifically for Mini-Agent systems evaluation.

This system evaluates agent-specific capabilities:
1. Multi-step task execution and reasoning
2. Tool selection and usage effectiveness  
3. Skills system integration
4. Agent conversation and context management
5. Error handling and recovery

CLEAR Framework Dimensions for Mini-Agent:
- Cost (C): LLM API calls, token usage, computational overhead
- Latency (L): Task completion time, tool execution delays, response speed
- Efficiency (E): Steps needed, tool selection accuracy, context utilization
- Assurance (A): Task completion accuracy, output quality, reasoning correctness  
- Reliability (R): Success rates, error handling, system stability

Uses proper mini-agent CLI interface with --task parameter for realistic testing.
"""

import asyncio
import json
import time
import traceback
import subprocess
import tempfile
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import threading

# Try to import psutil, but make it optional
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Import existing evaluation system
from advanced_evaluation_system import (
    AdvancedEvaluator,
    EvaluationCriteria,
    EvaluationResult
)

logger = logging.getLogger(__name__)


def _looks_like_mini_agent_process(process_name: str, cmd_parts: List[str]) -> bool:
    """Best-effort matcher for mini-agent processes across launcher variants."""
    normalized_name = Path(process_name or "").name.lower().replace("_", "-")
    normalized_parts = [
        Path(part).name.lower().replace("_", "-")
        for part in (cmd_parts or [])
        if part
    ]

    if "mini-agent" in normalized_name:
        return True

    if any(part in {"mini-agent", "mini-agent.exe"} for part in normalized_parts):
        return True

    lowered_cmd = [(part or "").lower() for part in (cmd_parts or [])]
    for idx, token in enumerate(lowered_cmd[:-1]):
        if token == "-m" and lowered_cmd[idx + 1].replace("_", "-") == "mini-agent":
            return True

    return "mini-agent" in " ".join(lowered_cmd).replace("_", "-")


@dataclass
class MiniAgentCLEARMetrics:
    """CLEAR Framework metrics specifically for Mini-Agent evaluation"""
    
    # Cost Dimension - API and computational costs
    llm_api_calls: int = 0
    total_tokens_used: int = 0
    tool_executions: int = 0
    skill_activations: int = 0
    estimated_cost_usd: float = 0.0
    context_window_usage: float = 0.0  # Percentage of context used
    
    # Latency Dimension - Time-based performance
    total_task_time: float = 0.0
    agent_thinking_time: float = 0.0
    tool_execution_time: float = 0.0
    llm_response_time: float = 0.0
    steps_to_completion: int = 0
    
    # Efficiency Dimension - Resource utilization and optimization
    task_efficiency_score: float = 0.0  # Task completion optimality
    tool_selection_accuracy: float = 0.0  # Correct tool choices
    context_utilization_ratio: float = 0.0  # Effective context usage
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    steps_per_second: float = 0.0
    
    # Assurance Dimension - Correctness and quality
    task_completion_accuracy: float = 0.0  # Did it complete the task correctly?
    output_quality_score: float = 0.0  # Quality of final output
    reasoning_coherence: float = 0.0  # Logical reasoning flow
    tool_usage_correctness: float = 0.0  # Appropriate tool usage
    skills_effectiveness: float = 0.0  # Skills system performance
    
    # Reliability Dimension - Stability and consistency
    execution_success_rate: float = 0.0
    error_recovery_effectiveness: float = 0.0
    response_consistency: float = 0.0  # Consistency across similar tasks
    system_stability: float = 0.0

@dataclass
class MiniAgentTestCriteria:
    """Test criteria specific to Mini-Agent evaluation"""
    
    # Task characteristics
    task_type: str = "general"  # "coding", "analysis", "file_ops", "reasoning", "skills"
    complexity: str = "medium"  # "simple", "medium", "complex"
    expected_tools: List[str] = field(default_factory=list)  # Expected tool usage
    expected_skills: List[str] = field(default_factory=list)  # Expected skills usage
    max_steps: int = 20  # Maximum reasonable steps
    
    # CLEAR weights (can be adjusted based on task type)
    cost_weight: float = 0.15
    latency_weight: float = 0.20
    efficiency_weight: float = 0.25  # Higher for agents
    assurance_weight: float = 0.25
    reliability_weight: float = 0.15
    
    # Performance thresholds
    max_task_time_seconds: float = 120.0
    max_cost_per_task: float = 0.50  # USD
    min_accuracy_threshold: float = 0.7
    max_acceptable_steps: int = 15

@dataclass
class MiniAgentTestCase:
    """Test case definition for Mini-Agent evaluation"""
    
    name: str
    category: str  # "coding", "analysis", "file_operations", "reasoning", "skills_usage"
    description: str
    task_prompt: str
    evaluation_criteria: MiniAgentTestCriteria = field(default_factory=MiniAgentTestCriteria)
    
    # Expected outcomes
    expected_outputs: List[str] = field(default_factory=list)
    expected_file_changes: List[str] = field(default_factory=list)
    success_indicators: List[str] = field(default_factory=list)
    
    # Ground truth for comparison
    ground_truth_answer: Optional[str] = None

@dataclass
class MiniAgentEvaluationResult:
    """Comprehensive evaluation result for Mini-Agent"""
    
    test_case: MiniAgentTestCase
    clear_metrics: MiniAgentCLEARMetrics
    evaluation_result: EvaluationResult
    
    # Mini-Agent specific results
    agent_output: str = ""
    agent_error_output: str = ""
    execution_logs: str = ""
    
    # Analysis
    tools_used: List[str] = field(default_factory=list)
    skills_used: List[str] = field(default_factory=list)
    step_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    
    # Performance summary
    overall_clear_score: float = 0.0
    passed_all_thresholds: bool = False
    confidence_score: float = 0.0
    
    # Insights
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    failed_criteria: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # Execution time breakdown: LLM inference / tool calls / coordination
    time_breakdown: Dict[str, Any] = field(default_factory=dict)

    # Per-step resource attribution correlated from timeline + monitor snapshots
    step_resource_profiles: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class StepResourceProfile:
    """Resource usage snapshot correlated to a specific agent timeline event"""
    step: Optional[int]
    event_type: str           # "thinking", "tool_call", "tool_result", "assistant_response", "error"
    time_offset_s: float      # seconds elapsed from task start when this event occurred (estimated)
    cpu_percent: float
    memory_mb: float


class MiniAgentResourceMonitor:
    """Resource monitoring specifically for Mini-Agent execution"""
    
    def __init__(self):
        self.monitoring = False
        self.start_time = 0.0
        self.peak_memory = 0.0
        self.cpu_samples = []
        self.mini_agent_process = None
        self.target_pid: Optional[int] = None
        self.monitor_thread = None
        # Timestamped snapshots: List of (abs_timestamp, memory_mb, cpu_pct)
        self.snapshots: List[Tuple[float, float, float]] = []

    def set_target_pid(self, pid: int):
        """Attach monitor to a known process PID."""
        self.target_pid = pid
        if not PSUTIL_AVAILABLE:
            return
        try:
            self.mini_agent_process = psutil.Process(pid)
            # Prime CPU accounting so subsequent samples are meaningful.
            self.mini_agent_process.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.mini_agent_process = None
        
    def start_monitoring(self):
        """Start monitoring mini-agent process resources"""
        self.monitoring = True
        self.start_time = time.time()
        self.peak_memory = 0.0
        self.cpu_samples = []
        self.snapshots = []
        self.mini_agent_process = None
        self.target_pid = None
        
        def monitor_loop():
            while self.monitoring:
                try:
                    ts = time.time()
                    memory_mb = 0.0
                    cpu_pct = 0.0

                    if PSUTIL_AVAILABLE:
                        # Prefer explicit PID attachment when available.
                        if self.mini_agent_process is None and self.target_pid is not None:
                            try:
                                self.mini_agent_process = psutil.Process(self.target_pid)
                                self.mini_agent_process.cpu_percent(interval=None)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                self.mini_agent_process = None

                        # Fallback discovery by executable token.
                        if self.mini_agent_process is None:
                            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                try:
                                    name = (proc.info.get('name') or '').lower()
                                    cmd_parts = proc.info.get('cmdline') or []
                                    if _looks_like_mini_agent_process(name, cmd_parts):
                                        self.mini_agent_process = psutil.Process(proc.info['pid'])
                                        self.mini_agent_process.cpu_percent(interval=None)
                                        break
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    continue

                        if self.mini_agent_process:
                            try:
                                memory_mb = self.mini_agent_process.memory_info().rss / 1024 / 1024
                                cpu_pct = self.mini_agent_process.cpu_percent()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                self.mini_agent_process = None

                    self.peak_memory = max(self.peak_memory, memory_mb)
                    self.cpu_samples.append(cpu_pct)
                    self.snapshots.append((ts, memory_mb, cpu_pct))

                    time.sleep(0.5)
                except Exception:
                    pass
                    
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> Tuple[float, float, float]:
        """Stop monitoring and return (duration, peak_memory_mb, avg_cpu_pct)"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
            
        duration = time.time() - self.start_time
        avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0.0
        
        return duration, self.peak_memory, avg_cpu

    def get_resource_at(self, abs_timestamp: float) -> Tuple[float, float]:
        """Return (memory_mb, cpu_pct) from the snapshot closest to abs_timestamp"""
        if not self.snapshots:
            return (0.0, 0.0)
        closest = min(self.snapshots, key=lambda s: abs(s[0] - abs_timestamp))
        return (closest[1], closest[2])

class MiniAgentLogAnalyzer:
    """Enhanced Mini-Agent log analyzer with multiple detection methods and log file access"""
    
    def __init__(self):
        # Multiple pattern approaches for robustness
        self.tool_call_patterns = [
            r"🔧 Tool Call: ([a-zA-Z_]+)",           # Primary pattern
            r"Tool Call: ([a-zA-Z_]+)",              # Alternative
            r'"name":\s*"([a-zA-Z_]+)"',             # JSON format in logs
            r"Tool:\s*([a-zA-Z_]+)",                 # Simpler format
        ]
        
        self.step_pattern = r"Step (\d+)/\d+"
        self.thinking_pattern = r"🧠 Thinking:"
        self.assistant_pattern = r"🤖 Assistant:"
        self.error_pattern = r"❌|✗ Error"
        self.tool_result_pattern = r"(?:✓|✅)\s*Result"
        
        # Session statistics pattern (from end of log)
        self.session_stats_pattern = r"Total Messages:\s*(\d+).*Tool Calls:\s*(\d+).*API Tokens Used:\s*([\d,]+)"
        
        # Real timing patterns from Mini-Agent logs
        self.session_duration_pattern = r"Session Duration: (\d{2}):(\d{2}):(\d{2})"
        
        # Known mini-agent tools for verification
        self.known_tools = [
            "read_file", "write_file", "edit_file", 
            "bash", "bash_output", "bash_kill",
            "record_note", "recall_notes", "get_skill"
        ]
    
    def analyze_execution_log(self, stdout_log: str, log_file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Enhanced log analysis with multiple detection methods and log file access
        
        Args:
            stdout_log: The stdout from mini-agent execution
            log_file_path: Optional path to the detailed log file in ~/.mini-agent/log/
        """
        
        analysis = {
            "total_steps": 0,
            "tools_used": [],
            "tool_call_count": 0,
            "thinking_blocks": 0,
            "assistant_responses": 0,
            "errors_encountered": 0,
            "successful_operations": 0,
            "step_breakdown": [],
            "execution_timeline": [],
            "session_stats": {},
            "log_sources": ["stdout"],
            "session_duration": {},    # Session timing from logs
            "tool_timings": [],       # List of {tool_name, estimated_duration}
            "detailed_timeline": []    # Chronological list of all events
        }
        
        # Analyze stdout log
        self._analyze_stdout_log(stdout_log, analysis)
        
        # Auto-detect log file from stdout if not provided
        if not log_file_path:
            log_file_path = self._extract_log_file_path(stdout_log)
        
        # Try to get more detailed info from log file
        if log_file_path and Path(log_file_path).exists():
            try:
                detailed_log = Path(log_file_path).read_text()
                self._analyze_detailed_log(detailed_log, analysis)
                analysis["log_sources"].append("detailed_log")
            except Exception as e:
                logger.warning(f"Could not read detailed log {log_file_path}: {e}")
        
        # Extract session statistics if available
        self._extract_session_stats(stdout_log, analysis)
        
        # Remove duplicates and clean up
        analysis["tools_used"] = list(dict.fromkeys(analysis["tools_used"]))  # Remove duplicates, preserve order
        analysis["tool_call_count"] = sum(
            1 for event in analysis["detailed_timeline"]
            if event.get("event_type") == "tool_call"
        )
        
        return analysis
    
    def _analyze_stdout_log(self, log_text: str, analysis: Dict[str, Any]):
        """Analyze the stdout log text with detailed timing extraction"""
        
        lines = log_text.split('\n')
        current_step = None
        current_step_tools = []
        
        for i, line in enumerate(lines):
            # Track steps
            step_match = re.search(self.step_pattern, line)
            if step_match:
                step_num = int(step_match.group(1))
                analysis["total_steps"] = max(analysis["total_steps"], step_num)
                analysis["step_breakdown"].append({"step": step_num, "line": i, "text": line.strip()})
                current_step = step_num
                current_step_tools = []
            
            # Track session duration information
            duration_match = re.search(self.session_duration_pattern, line)
            if duration_match:
                hours = int(duration_match.group(1))
                minutes = int(duration_match.group(2))
                seconds = int(duration_match.group(3))
                total_seconds = hours * 3600 + minutes * 60 + seconds
                
                analysis["session_duration"] = {
                    "hours": hours,
                    "minutes": minutes,
                    "seconds": seconds,
                    "total_seconds": total_seconds
                }
            
            # Track tool calls with multiple patterns
            tool_found_in_line = None
            for pattern in self.tool_call_patterns:
                tool_match = re.search(pattern, line)
                if tool_match:
                    tool_name = tool_match.group(1)
                    if tool_name in self.known_tools:
                        if tool_name not in analysis["tools_used"]:
                            analysis["tools_used"].append(tool_name)
                        if current_step and tool_name not in current_step_tools:
                            current_step_tools.append(tool_name)
                        tool_found_in_line = tool_name
                        break  # Found with this pattern, no need to try others
            
            # Add tool call to timeline if found
            if tool_found_in_line:
                analysis["detailed_timeline"].append({
                    "event_type": "tool_call",
                    "tool_name": tool_found_in_line,
                    "step": current_step,
                    "line": i,
                    "text": line.strip()
                })
            
            # Track other elements
            if re.search(self.thinking_pattern, line):
                analysis["thinking_blocks"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "thinking",
                    "step": current_step,
                    "line": i
                })
                
            if re.search(self.assistant_pattern, line):
                analysis["assistant_responses"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "assistant_response", 
                    "step": current_step,
                    "line": i
                })
            
            if re.search(self.error_pattern, line):
                analysis["errors_encountered"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "error",
                    "step": current_step,
                    "line": i,
                    "text": line.strip()
                })
            
            if re.search(self.tool_result_pattern, line):
                analysis["successful_operations"] += 1
                if current_step is not None:
                    analysis["detailed_timeline"].append({
                        "event_type": "tool_result",
                        "step": current_step,
                        "line": i
                    })
        
        # Update total tool-call count before timing estimation.
        analysis["tool_call_count"] = sum(
            1 for event in analysis["detailed_timeline"]
            if event.get("event_type") == "tool_call"
        )

        # Calculate tool-specific timing estimates
        self._estimate_tool_timings(analysis)
    
    def _estimate_tool_timings(self, analysis: Dict[str, Any]):
        """Estimate timing for each tool call based on available timing data"""
        
        # Use session duration to estimate tool timing
        session_duration = analysis.get("session_duration") or {}
        total_session_time = session_duration.get("total_seconds")

        if total_session_time is not None and analysis["tool_call_count"] > 0:
            total_tools = analysis["tool_call_count"]
            
            # Simple estimation: divide session time among tools
            # Account for LLM thinking time (assume 70% of session is LLM, 30% tools)
            estimated_tool_time_total = total_session_time * 0.3
            estimated_per_tool = estimated_tool_time_total / total_tools if total_tools > 0 else 0
            
            # Create timing estimates for each tool
            for tool_name in analysis["tools_used"]:
                analysis["tool_timings"].append({
                    "tool_name": tool_name,
                    "estimated_duration": estimated_per_tool,
                    "total_session_duration": total_session_time
                })
    
    def _analyze_detailed_log(self, log_text: str, analysis: Dict[str, Any]):
        """Analyze the detailed log file for additional information"""
        
        # Look for more detailed tool call information in JSON format
        json_tool_pattern = r'"tool_name":\s*"([a-zA-Z_]+)"'
        json_matches = re.findall(json_tool_pattern, log_text)
        
        for tool_name in json_matches:
            if tool_name in self.known_tools and tool_name not in analysis["tools_used"]:
                analysis["tools_used"].append(tool_name)
        
        # Look for function call patterns
        function_pattern = r'function":\s*{\s*"name":\s*"([a-zA-Z_]+)"'
        function_matches = re.findall(function_pattern, log_text)
        
        for tool_name in function_matches:
            if tool_name in self.known_tools and tool_name not in analysis["tools_used"]:
                analysis["tools_used"].append(tool_name)
    
    def _extract_log_file_path(self, stdout_log: str) -> Optional[str]:
        """Extract the log file path from stdout"""
        
        # Look for log file path in stdout
        log_pattern = r"📝 Log file: (.+\.log)"
        match = re.search(log_pattern, stdout_log)
        
        if match:
            log_path = match.group(1).strip()
            # Expand user directory
            if log_path.startswith("~/"):
                log_path = str(Path.home()) + log_path[1:]
            return log_path
        
        return None
    
    def _extract_session_stats(self, log_text: str, analysis: Dict[str, Any]):
        """Extract session statistics from the end of the log"""
        
        # Look for the session statistics block
        stats_match = re.search(self.session_stats_pattern, log_text, re.DOTALL)
        
        if stats_match:
            try:
                total_messages = int(stats_match.group(1))
                tool_calls = int(stats_match.group(2))
                tokens_used = int(stats_match.group(3).replace(',', ''))
                
                analysis["session_stats"] = {
                    "total_messages": total_messages,
                    "tool_calls": tool_calls,
                    "tokens_used": tokens_used
                }
                
                # Use session stats to verify our tool count
                if tool_calls > 0 and len(analysis["tools_used"]) == 0:
                    logger.warning(f"Session stats show {tool_calls} tool calls but none detected by pattern matching")
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Could not parse session statistics: {e}")

class MiniAgentCLEAREvaluator:
    """
    Comprehensive Mini-Agent evaluation system implementing CLEAR Framework
    specifically designed for agent systems evaluation
    """
    
    def __init__(self, results_dir: str = "mini_agent_evaluation_results", 
                 mini_agent_path: Optional[str] = None):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        
        # Auto-detect mini-agent path
        if mini_agent_path is None:
            import sys, shutil
            possible_paths = [
                # Windows conda env (common Miniconda/Anaconda locations)
                r"D:\Apps\Miniconda\envs\mini-agent\Scripts\mini-agent.exe",
                r"C:\ProgramData\Miniconda3\envs\mini-agent\Scripts\mini-agent.exe",
                r"C:\Users\Hanne\Miniconda3\envs\mini-agent\Scripts\mini-agent.exe",
                # macOS / Linux venv (kept for cross-platform compat)
                "/Users/ria/Downloads/UCSD/CSE291P/Team28/Mini-Agent/.venv/bin/mini-agent",
                "./Mini-Agent/.venv/bin/mini-agent",
            ]

            found = None
            # 1. Check explicit paths
            for path in possible_paths:
                if Path(path).exists():
                    found = path
                    break

            # 2. Check PATH (works if conda env is activated)
            if found is None:
                found = shutil.which("mini-agent")

            # 3. Try conda run as fallback (works without activating env)
            if found is None:
                try:
                    test = subprocess.run(
                        ["conda", "run", "-n", "mini-agent", "mini-agent", "--version"],
                        capture_output=True, text=True
                    )
                    if test.returncode == 0:
                        found = "__conda_run__"  # special sentinel
                except FileNotFoundError:
                    # conda is optional; we'll continue to the unified RuntimeError below.
                    pass

            if found is None:
                raise RuntimeError(
                    "Could not find mini-agent executable. "
                    "Run: conda activate mini-agent  then re-run, "
                    "or pass mini_agent_path= explicitly."
                )

            self.mini_agent_path = found
            self._use_conda_run = (found == "__conda_run__")
        else:
            self.mini_agent_path = mini_agent_path
            self._use_conda_run = False
            
        # Initialize components
        self.advanced_evaluator = AdvancedEvaluator(use_llm_judge=False)
        self.resource_monitor = MiniAgentResourceMonitor()
        self.log_analyzer = MiniAgentLogAnalyzer()
        
        # Logging setup
        logging.basicConfig(level=logging.INFO)
        logger.info(f"Mini-Agent path: {self.mini_agent_path}")
    
    def create_mini_agent_test_suite(self) -> List[MiniAgentTestCase]:
        """Create comprehensive test cases for Mini-Agent evaluation"""
        
        test_cases = []
        
        # 1. Simple File Operations
        test_cases.append(MiniAgentTestCase(
            name="simple_file_operations",
            category="file_operations",
            description="Create, modify, and read files to test basic tool usage",
            task_prompt="""Please help me with these file operations:
1. Create a file called 'test_data.txt' with the numbers 1, 2, 3, 4, 5 (one per line)
2. Read the file back and calculate the sum of all numbers
3. Create another file called 'result.txt' with the calculated sum
4. Show me the contents of both files to confirm they were created correctly""",
            evaluation_criteria=MiniAgentTestCriteria(
                task_type="file_ops",
                complexity="simple",
                expected_tools=["write_file", "read_file"],
                max_steps=8,
                cost_weight=0.1,
                latency_weight=0.2,
                efficiency_weight=0.3,
                assurance_weight=0.3,
                reliability_weight=0.1
            ),
            expected_outputs=["test_data.txt", "result.txt", "15"],
            expected_file_changes=["test_data.txt", "result.txt"],
            success_indicators=["sum", "15", "contents", "created"],
            ground_truth_answer="Should create test_data.txt with numbers 1-5, calculate sum (15), create result.txt with sum, and display both file contents."
        ))
        
        # 2. Coding Task with Analysis
        test_cases.append(MiniAgentTestCase(
            name="python_coding_task",
            category="coding",
            description="Write, execute, and debug a Python script",
            task_prompt="""I need help creating a Python script that:
1. Defines a function called 'calculate_fibonacci' that takes a number n and returns the nth Fibonacci number
2. Tests the function with n=10
3. Saves the script as 'fibonacci.py'
4. Runs the script to show it works correctly
5. If there are any errors, fix them

Please show me the complete process including testing.""",
            evaluation_criteria=MiniAgentTestCriteria(
                task_type="coding",
                complexity="medium",
                expected_tools=["write_file", "bash", "read_file"],
                max_steps=12,
                cost_weight=0.15,
                latency_weight=0.2,
                efficiency_weight=0.25,
                assurance_weight=0.3,
                reliability_weight=0.1
            ),
            expected_outputs=["fibonacci.py", "function", "55"],
            expected_file_changes=["fibonacci.py"],
            success_indicators=["function", "fibonacci", "55", "works correctly"],
            ground_truth_answer="Should create fibonacci.py with correct Fibonacci function, test with n=10 (result: 55), and demonstrate successful execution."
        ))
        
        # 3. Multi-step Analysis Task
        test_cases.append(MiniAgentTestCase(
            name="data_analysis_task",
            category="analysis",
            description="Analyze data and generate insights with multiple steps",
            task_prompt="""Please help me analyze some sample data:

1. Create a CSV file called 'sales_data.csv' with this data:
   - Headers: Month, Sales, Profit
   - Data rows:
     January,10000,2000
     February,12000,2400
     March,9000,1800
     April,15000,3000
     May,11000,2200

2. Write a Python script that:
   - Reads the CSV file
   - Calculates total sales and profit
   - Finds the month with highest sales
   - Calculates average monthly profit
   - Saves results to 'analysis_results.txt'

3. Run the script and show me the analysis results""",
            evaluation_criteria=MiniAgentTestCriteria(
                task_type="analysis",
                complexity="complex",
                expected_tools=["write_file", "read_file", "bash"],
                max_steps=15,
                cost_weight=0.2,
                latency_weight=0.15,
                efficiency_weight=0.25,
                assurance_weight=0.3,
                reliability_weight=0.1
            ),
            expected_outputs=["sales_data.csv", "analysis_results.txt", "57000", "11400", "April"],
            expected_file_changes=["sales_data.csv", "analysis_results.txt"],
            success_indicators=["57000", "11400", "April", "average", "analysis"],
            ground_truth_answer="Should create CSV file, write analysis script, calculate total sales (57000), total profit (11400), identify April as highest sales month, calculate average profit (2280), and generate results file."
        ))
        
        # 4. Error Handling and Recovery
        test_cases.append(MiniAgentTestCase(
            name="error_handling_test",
            category="reasoning",
            description="Test agent's ability to handle errors and adapt",
            task_prompt="""I need you to help me with a task that might have some issues:

1. Try to read a file called 'nonexistent.txt' 
2. When that fails (as it should), create the file with some sample content
3. Read the file you just created to confirm it works
4. Try to run a Python command that has a syntax error: 'python -c "print(hello world"'
5. Fix the syntax error and run the corrected command
6. Summarize what went wrong and how you fixed the issues""",
            evaluation_criteria=MiniAgentTestCriteria(
                task_type="reasoning",
                complexity="medium",
                expected_tools=["read_file", "write_file", "bash"],
                max_steps=12,
                cost_weight=0.1,
                latency_weight=0.2,
                efficiency_weight=0.2,
                assurance_weight=0.25,
                reliability_weight=0.25  # Higher weight on reliability
            ),
            expected_outputs=["nonexistent.txt", "syntax error", "fixed"],
            expected_file_changes=["nonexistent.txt"],
            success_indicators=["error", "fixed", "created", "summarize", "issues"],
            ground_truth_answer="Should handle file not found error by creating the file, identify and fix the Python syntax error, and provide a clear summary of problems encountered and solutions applied."
        ))
        
        # 5. Skills System Usage (if available)
        test_cases.append(MiniAgentTestCase(
            name="skills_integration_test",
            category="skills_usage",
            description="Test integration with Mini-Agent skills system",
            task_prompt="""Please help me test the skills system:

1. Try to use the get_skill tool to get information about available document skills
2. Use any document-related skill to create or process a document  
3. If no document skills are available, create a simple text document and process it manually
4. Provide a summary of what skills were used and how they performed""",
            evaluation_criteria=MiniAgentTestCriteria(
                task_type="skills",
                complexity="medium",
                expected_tools=["get_skill", "write_file", "read_file"],
                expected_skills=["document-skills"],
                max_steps=10,
                cost_weight=0.15,
                latency_weight=0.2,
                efficiency_weight=0.25,
                assurance_weight=0.25,
                reliability_weight=0.15
            ),
            expected_outputs=["skills", "document", "summary"],
            success_indicators=["skills", "available", "used", "performed"],
            ground_truth_answer="Should list available skills, demonstrate skill usage (or fallback to manual processing), and provide clear summary of skills system interaction."
        ))
        
        return test_cases
    
    async def execute_mini_agent_task(self, test_case: MiniAgentTestCase) -> Tuple[str, str, bool, float]:
        """
        Execute Mini-Agent task using proper CLI interface
        Returns: (stdout, stderr, success, execution_time)
        """
        
        start_time = time.time()
        
        try:
            with tempfile.TemporaryDirectory() as temp_workspace:
                process = None
                
                if getattr(self, "_use_conda_run", False):
                    cmd = [
                        "conda", "run", "-n", "mini-agent", "mini-agent",
                        "--workspace", temp_workspace,
                        "--task", test_case.task_prompt,
                    ]
                else:
                    cmd = [
                        self.mini_agent_path,
                        "--workspace", temp_workspace,
                        "--task", test_case.task_prompt,
                    ]

                logger.info(f"Executing: {' '.join(cmd[:4])} ...")

                # Execute mini-agent with task.
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=temp_workspace,
                )
                self._bind_monitor_target_pid(process.pid, conda_mode=getattr(self, "_use_conda_run", False))

                try:
                    stdout, stderr = process.communicate(
                        timeout=test_case.evaluation_criteria.max_task_time_seconds
                    )
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    execution_time = time.time() - start_time
                    timeout_msg = (
                        f"Task timed out after "
                        f"{test_case.evaluation_criteria.max_task_time_seconds} seconds"
                    )
                    combined_stderr = f"{stderr}\n{timeout_msg}" if stderr else timeout_msg
                    return stdout or "", combined_stderr, False, execution_time
                
                execution_time = time.time() - start_time
                success = process.returncode == 0
                
                # Check for expected file changes in workspace
                expected_files_found = []
                for expected_file in test_case.expected_file_changes:
                    file_path = Path(temp_workspace) / expected_file
                    if file_path.exists():
                        expected_files_found.append(expected_file)
                        # Read file content for analysis
                        try:
                            content = file_path.read_text()
                            # Append file content to stdout for analysis
                            stdout = (stdout or "") + f"\n[FILE_CONTENT:{expected_file}]\n{content}\n[/FILE_CONTENT]"
                        except:
                            pass
                
                return stdout or "", stderr or "", success, execution_time
                
        except Exception as e:
            execution_time = time.time() - start_time
            return "", f"Execution error: {str(e)}", False, execution_time

    def _bind_monitor_target_pid(self, launcher_pid: int, conda_mode: bool) -> None:
        """
        Bind resource monitor to the best target PID.

        - direct mode: bind to launcher pid directly (mini-agent itself)
        - conda mode: launcher is usually `conda`; try to find the spawned mini-agent child
        """
        if not PSUTIL_AVAILABLE:
            return

        if not conda_mode:
            self.resource_monitor.set_target_pid(launcher_pid)
            return

        try:
            launcher = psutil.Process(launcher_pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return

        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                children = launcher.children(recursive=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                children = []

            for child in children:
                try:
                    name = (child.name() or "").lower()
                    cmd_parts = child.cmdline() or []
                    if _looks_like_mini_agent_process(name, cmd_parts):
                        self.resource_monitor.set_target_pid(child.pid)
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            time.sleep(0.1)
    
    async def evaluate_mini_agent_test(self, test_case: MiniAgentTestCase) -> MiniAgentEvaluationResult:
        """
        Comprehensive evaluation of Mini-Agent test case using CLEAR Framework
        """
        
        logger.info(f"Evaluating Mini-Agent test: {test_case.name}")
        
        # Initialize metrics
        clear_metrics = MiniAgentCLEARMetrics()
        
        # Start resource monitoring
        self.resource_monitor.start_monitoring()
        
        try:
            # Execute Mini-Agent task — record wall-clock start for correlation later
            task_start_time = time.time()
            stdout, stderr, success, execution_time = await self.execute_mini_agent_task(test_case)
            
            # Stop resource monitoring
            _, peak_memory, avg_cpu = self.resource_monitor.stop_monitoring()
            
            # Defensive: ensure stdout/stderr are always strings (guards against subprocess edge cases)
            stdout = stdout or ""
            stderr = stderr or ""

            # Analyze execution logs with enhanced detection
            log_analysis = self.log_analyzer.analyze_execution_log(stdout + "\n" + stderr)
            
            # Debug information
            logger.info(f"Log analysis results for {test_case.name}:")
            logger.info(f"  Tools detected: {log_analysis['tools_used']}")
            logger.info(f"  Tool call count: {log_analysis['tool_call_count']}")
            logger.info(f"  Session stats: {log_analysis.get('session_stats', 'Not available')}")
            logger.info(f"  Log sources: {log_analysis['log_sources']}")
            
            # Populate CLEAR metrics
            
            # Cost Dimension - Use session stats if available, otherwise estimate
            if "session_stats" in log_analysis and "tokens_used" in log_analysis["session_stats"]:
                clear_metrics.total_tokens_used = log_analysis["session_stats"]["tokens_used"]
                clear_metrics.tool_executions = log_analysis["session_stats"]["tool_calls"]
            else:
                clear_metrics.total_tokens_used = self._estimate_token_usage(test_case.task_prompt + stdout)
                clear_metrics.tool_executions = log_analysis["tool_call_count"]
            
            clear_metrics.llm_api_calls = log_analysis["thinking_blocks"] + log_analysis["total_steps"]
            clear_metrics.estimated_cost_usd = self._estimate_cost(clear_metrics.total_tokens_used, clear_metrics.llm_api_calls)
            
            # Latency Dimension
            clear_metrics.total_task_time = execution_time
            clear_metrics.steps_to_completion = log_analysis["total_steps"]

            # Compute time breakdown using timeline-weighted method (replaces hardcoded 70/30)
            time_breakdown = self._calculate_time_breakdown(log_analysis, execution_time)
            clear_metrics.tool_execution_time = time_breakdown["tool_execution_s"]
            clear_metrics.llm_response_time = time_breakdown["llm_inference_s"]
            clear_metrics.agent_thinking_time = time_breakdown["llm_inference_s"]  # same concept
            
            # Efficiency Dimension
            clear_metrics.memory_usage_mb = peak_memory
            clear_metrics.cpu_usage_percent = avg_cpu
            clear_metrics.steps_per_second = log_analysis["total_steps"] / max(execution_time, 0.1)
            clear_metrics.tool_selection_accuracy = self._calculate_tool_accuracy(
                log_analysis["tools_used"], 
                test_case.evaluation_criteria.expected_tools
            )
            clear_metrics.task_efficiency_score = self._calculate_efficiency_score(
                log_analysis["total_steps"], 
                test_case.evaluation_criteria.max_acceptable_steps
            )
            
            # Assurance Dimension - Use advanced evaluator
            evaluation_criteria = EvaluationCriteria(
                evaluation_type="hybrid",
                expected_keywords=test_case.success_indicators + test_case.expected_outputs,
                correctness_weight=0.4,
                completeness_weight=0.3,
                reasoning_weight=0.3
            )
            
            evaluation_result = self.advanced_evaluator.evaluate_response(
                task_prompt=test_case.task_prompt,
                agent_response=stdout,
                criteria=evaluation_criteria,
                execution_time=execution_time
            )
            
            # Map to CLEAR Assurance metrics
            clear_metrics.task_completion_accuracy = evaluation_result.correctness_score
            clear_metrics.output_quality_score = max(0.0, min(1.0, evaluation_result.overall_score))
            clear_metrics.reasoning_coherence = evaluation_result.reasoning_score
            clear_metrics.tool_usage_correctness = min(1.0, clear_metrics.tool_selection_accuracy + 0.2)
            
            # Reliability Dimension
            clear_metrics.execution_success_rate = 1.0 if success else 0.0
            clear_metrics.error_recovery_effectiveness = self._calculate_error_recovery(
                log_analysis["errors_encountered"],
                log_analysis["successful_operations"]
            )
            clear_metrics.system_stability = 1.0 - (log_analysis["errors_encountered"] / max(log_analysis["total_steps"], 1))
            clear_metrics.response_consistency = 0.8  # Placeholder - would need multiple runs
            
            # Calculate dimension scores
            dimension_scores = self._calculate_mini_agent_dimension_scores(clear_metrics, test_case.evaluation_criteria)
            
            # Calculate overall CLEAR score
            criteria = test_case.evaluation_criteria
            overall_clear_score = (
                dimension_scores['cost'] * criteria.cost_weight +
                dimension_scores['latency'] * criteria.latency_weight +
                dimension_scores['efficiency'] * criteria.efficiency_weight +
                dimension_scores['assurance'] * criteria.assurance_weight +
                dimension_scores['reliability'] * criteria.reliability_weight
            )
            
            # Check threshold compliance
            passed_thresholds = (
                clear_metrics.total_task_time <= criteria.max_task_time_seconds and
                clear_metrics.task_completion_accuracy >= criteria.min_accuracy_threshold and
                clear_metrics.estimated_cost_usd <= criteria.max_cost_per_task and
                clear_metrics.steps_to_completion <= criteria.max_acceptable_steps
            )
            
            # Generate recommendations
            recommendations = self._generate_mini_agent_recommendations(clear_metrics, test_case.evaluation_criteria)
            
            # Per-step resource attribution
            step_resource_profiles = self._build_step_resource_profiles(
                log_analysis, task_start_time, execution_time, self.resource_monitor
            )

            # Create result
            result = MiniAgentEvaluationResult(
                test_case=test_case,
                clear_metrics=clear_metrics,
                evaluation_result=evaluation_result,
                agent_output=stdout,
                agent_error_output=stderr,
                execution_logs=stdout + "\n--- STDERR ---\n" + stderr,
                tools_used=list(dict.fromkeys(log_analysis["tools_used"])),
                step_breakdown=log_analysis["step_breakdown"],
                overall_clear_score=overall_clear_score,
                passed_all_thresholds=passed_thresholds,
                confidence_score=evaluation_result.confidence,
                dimension_scores=dimension_scores,
                recommendations=recommendations,
                time_breakdown=time_breakdown,
                step_resource_profiles=step_resource_profiles,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Evaluation failed for {test_case.name}: {e}")
            # Return error result
            return MiniAgentEvaluationResult(
                test_case=test_case,
                clear_metrics=MiniAgentCLEARMetrics(),
                evaluation_result=EvaluationResult(overall_score=0.0),
                agent_output="",
                agent_error_output=f"Evaluation error: {str(e)}",
                execution_logs=traceback.format_exc(),
                overall_clear_score=0.0,
                passed_all_thresholds=False,
                confidence_score=0.0,
                dimension_scores={},
                recommendations=["Fix evaluation system errors"]
            )
    
    def _estimate_token_usage(self, text: str) -> int:
        """Estimate token usage from text (rough approximation)"""
        return int(len(text.split()) * 1.3)  # ~1.3 tokens per word
    
    def _estimate_cost(self, tokens: int, api_calls: int) -> float:
        """Estimate cost in USD based on typical LLM pricing"""
        # Rough estimate: $0.002 per 1K tokens + $0.001 per API call overhead
        return (tokens * 0.002 / 1000) + (api_calls * 0.001)
    
    def _calculate_tool_accuracy(self, tools_used: List[str], expected_tools: List[str]) -> float:
        """Calculate how well the agent selected appropriate tools"""
        if not expected_tools:
            return 1.0  # No expectations, so can't be wrong
        
        # Check if expected tools were used
        expected_used = sum(1 for tool in expected_tools if tool in tools_used)
        accuracy = expected_used / len(expected_tools)
        
        # Penalize for using too many unnecessary tools
        if len(tools_used) > len(expected_tools) * 1.5:
            accuracy *= 0.8
        
        return min(1.0, accuracy)
    
    def _calculate_efficiency_score(self, actual_steps: int, max_steps: int) -> float:
        """Calculate task efficiency based on steps used"""
        if actual_steps == 0:
            return 0.0
        if actual_steps <= max_steps * 0.5:
            return 1.0  # Very efficient
        elif actual_steps <= max_steps:
            return 1.0 - ((actual_steps - max_steps * 0.5) / (max_steps * 0.5)) * 0.3
        else:
            return max(0.0, 0.7 - ((actual_steps - max_steps) / max_steps) * 0.7)
    
    def _calculate_error_recovery(self, errors: int, successes: int) -> float:
        """Calculate how well the agent recovered from errors"""
        total_ops = errors + successes
        if total_ops == 0:
            return 1.0
        if errors == 0:
            return 1.0
        return min(1.0, successes / total_ops)
    
    def _calculate_mini_agent_dimension_scores(self, metrics: MiniAgentCLEARMetrics, 
                                             criteria: MiniAgentTestCriteria) -> Dict[str, float]:
        """Calculate normalized CLEAR dimension scores for Mini-Agent"""
        
        scores = {}
        
        # Cost Score
        cost_ratio = metrics.estimated_cost_usd / criteria.max_cost_per_task
        scores['cost'] = max(0.0, 1.0 - cost_ratio)
        
        # Latency Score  
        time_ratio = metrics.total_task_time / criteria.max_task_time_seconds
        scores['latency'] = max(0.0, 1.0 - time_ratio)
        
        # Efficiency Score
        efficiency_components = [
            metrics.task_efficiency_score,
            metrics.tool_selection_accuracy,
            min(1.0, metrics.steps_per_second * 10),  # Normalize steps per second
            max(0.0, 1.0 - metrics.memory_usage_mb / 1000)  # Penalize high memory
        ]
        scores['efficiency'] = sum(efficiency_components) / len(efficiency_components)
        
        # Assurance Score
        assurance_components = [
            metrics.task_completion_accuracy,
            metrics.output_quality_score,
            metrics.reasoning_coherence,
            metrics.tool_usage_correctness
        ]
        scores['assurance'] = sum(assurance_components) / len(assurance_components)
        
        # Reliability Score
        reliability_components = [
            metrics.execution_success_rate,
            metrics.error_recovery_effectiveness,
            metrics.system_stability,
            metrics.response_consistency
        ]
        scores['reliability'] = sum(reliability_components) / len(reliability_components)
        
        return scores
    
    def _generate_mini_agent_recommendations(self, metrics: MiniAgentCLEARMetrics, 
                                           criteria: MiniAgentTestCriteria) -> List[str]:
        """Generate specific recommendations for Mini-Agent optimization"""
        
        recommendations = []
        
        # Cost recommendations
        if metrics.estimated_cost_usd > criteria.max_cost_per_task * 0.8:
            recommendations.append(f"💰 Optimize token usage - cost ${metrics.estimated_cost_usd:.3f} approaching limit ${criteria.max_cost_per_task:.3f}")
        
        # Latency recommendations
        if metrics.total_task_time > criteria.max_task_time_seconds * 0.7:
            recommendations.append(f"⚡ Task taking too long - {metrics.total_task_time:.1f}s vs {criteria.max_task_time_seconds}s limit")
        
        if metrics.steps_to_completion > criteria.max_acceptable_steps:
            recommendations.append(f"🔄 Too many steps - {metrics.steps_to_completion} vs {criteria.max_acceptable_steps} max")
        
        # Efficiency recommendations
        if metrics.tool_selection_accuracy < 0.7:
            recommendations.append(f"🔧 Improve tool selection - accuracy {metrics.tool_selection_accuracy:.2f}")
        
        if metrics.task_efficiency_score < 0.6:
            recommendations.append("📈 Optimize task execution - too many unnecessary steps")
        
        # Assurance recommendations
        if metrics.task_completion_accuracy < criteria.min_accuracy_threshold:
            recommendations.append(f"✅ Improve task completion - accuracy {metrics.task_completion_accuracy:.2f} below {criteria.min_accuracy_threshold}")
        
        if metrics.reasoning_coherence < 0.6:
            recommendations.append("🧠 Enhance reasoning quality - improve step-by-step thinking")
        
        # Reliability recommendations  
        if metrics.execution_success_rate < 1.0:
            recommendations.append("🛠️ Address execution failures - improve error handling")
        
        if metrics.error_recovery_effectiveness < 0.7:
            recommendations.append("🔄 Improve error recovery - better adaptation to failures")
        
        if not recommendations:
            recommendations.append("✨ Excellent performance across all dimensions!")
        
        return recommendations

    def _calculate_time_breakdown(self, log_analysis: Dict[str, Any], execution_time: float) -> Dict[str, Any]:
        """
        Compute LLM inference / tool execution / coordination time split.

        Strategy: each event in the detailed_timeline is assigned a 'weight' based on
        its type. Weights reflect typical duration profiles:
          - thinking / assistant_response  → weight 3  (API round-trip dominates)
          - tool_call / tool_result        → weight 1  (local or fast shell ops)
          - coordination (step markers,
            errors, etc.)                 → weight 0.5 (bookkeeping overhead)

        The fraction of total weight for each category becomes the fraction of time.
        Falls back to a fixed 70/20/10 estimate if no timeline is available.
        """
        timeline = log_analysis.get("detailed_timeline", [])

        LLM_TYPES = {"thinking", "assistant_response"}
        TOOL_TYPES = {"tool_call", "tool_result"}

        if not timeline:
            llm_s = round(execution_time * 0.70, 2)
            tool_s = round(execution_time * 0.20, 2)
            coord_s = round(execution_time * 0.10, 2)
            return {
                "llm_inference_s": llm_s,
                "tool_execution_s": tool_s,
                "coordination_s": coord_s,
                "llm_inference_pct": 70.0,
                "tool_execution_pct": 20.0,
                "coordination_pct": 10.0,
                "method": "fixed_estimate (no timeline)",
            }

        llm_w = sum(3 for e in timeline if e["event_type"] in LLM_TYPES)
        tool_w = sum(1 for e in timeline if e["event_type"] in TOOL_TYPES)
        coord_w = sum(0.5 for e in timeline if e["event_type"] not in LLM_TYPES | TOOL_TYPES)
        coord_w += 1.0  # baseline so coordination is never zero

        total_w = llm_w + tool_w + coord_w or 1.0

        llm_s = round(execution_time * llm_w / total_w, 2)
        tool_s = round(execution_time * tool_w / total_w, 2)
        coord_s = round(execution_time - llm_s - tool_s, 2)  # absorb rounding error

        return {
            "llm_inference_s": llm_s,
            "tool_execution_s": tool_s,
            "coordination_s": coord_s,
            "llm_inference_pct": round(100 * llm_s / execution_time, 1) if execution_time else 0.0,
            "tool_execution_pct": round(100 * tool_s / execution_time, 1) if execution_time else 0.0,
            "coordination_pct": round(100 * coord_s / execution_time, 1) if execution_time else 0.0,
            "method": "timeline_weighted",
            "llm_events": sum(1 for e in timeline if e["event_type"] in LLM_TYPES),
            "tool_events": sum(1 for e in timeline if e["event_type"] in TOOL_TYPES),
            "coord_events": sum(1 for e in timeline if e["event_type"] not in LLM_TYPES | TOOL_TYPES),
        }

    def _build_step_resource_profiles(
        self,
        log_analysis: Dict[str, Any],
        task_start_time: float,
        execution_time: float,
        resource_monitor: "MiniAgentResourceMonitor",
    ) -> List[Dict[str, Any]]:
        """
        Correlate each timeline event with the closest resource snapshot.

        Event line numbers are used to linearly interpolate a wall-clock timestamp:
            event_abs_time = task_start_time + (line / max_line) * execution_time

        The resource monitor's snapshot list is then searched for the nearest sample.
        """
        timeline = log_analysis.get("detailed_timeline", [])
        if not timeline:
            return []

        max_line = max((e.get("line", 0) for e in timeline), default=1) or 1
        profiles = []

        for event in timeline:
            line_num = event.get("line", 0)
            time_offset = (line_num / max_line) * execution_time
            abs_ts = task_start_time + time_offset

            memory_mb, cpu_pct = resource_monitor.get_resource_at(abs_ts)

            profiles.append({
                "step": event.get("step"),
                "event_type": event["event_type"],
                "time_offset_s": round(time_offset, 2),
                "cpu_percent": round(cpu_pct, 1),
                "memory_mb": round(memory_mb, 1),
            })

        return profiles

    async def run_comprehensive_mini_agent_evaluation(self) -> List[MiniAgentEvaluationResult]:
        """Run comprehensive Mini-Agent evaluation with CLEAR Framework"""
        
        print("🤖 Mini-Agent Comprehensive Evaluation with CLEAR Framework")
        print("=" * 80)
        print("Evaluating agent system across 5 key dimensions:")
        print("💰 Cost | ⚡ Latency | 📈 Efficiency | ✅ Assurance | 🛠️ Reliability")
        print("=" * 80)
        
        test_cases = self.create_mini_agent_test_suite()
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[{i}/{len(test_cases)}] Testing: {test_case.name} ({test_case.category})")
            print(f"📋 {test_case.description}")
            print(f"🎯 Expected tools: {test_case.evaluation_criteria.expected_tools}")
            
            result = await self.evaluate_mini_agent_test(test_case)
            results.append(result)
            
            # Print immediate summary
            status = "✅ PASS" if result.passed_all_thresholds else "❌ FAIL"
            print(f"   {status} | CLEAR Score: {result.overall_clear_score:.3f} | Confidence: {result.confidence_score:.3f}")
            print(f"   💰 ${result.clear_metrics.estimated_cost_usd:.3f} | ⚡ {result.clear_metrics.total_task_time:.1f}s | 🔧 {len(result.tools_used)} tools | 🔄 {result.clear_metrics.steps_to_completion} steps")
            
            # Save result
            await self._save_mini_agent_result(result)
        
        # Generate comprehensive report
        await self._generate_mini_agent_report(results)
        
        return results
    
    async def _save_mini_agent_result(self, result: MiniAgentEvaluationResult):
        """Save detailed Mini-Agent evaluation result"""
        
        timestamp = int(time.time())
        filename = f"mini_agent_{result.test_case.name}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        result_dict = {
            "schema_version": "phase3.v2",
            "test_case": {
                "name": result.test_case.name,
                "category": result.test_case.category,
                "description": result.test_case.description,
                "task_prompt": result.test_case.task_prompt
            },
            "clear_metrics": asdict(result.clear_metrics),
            "execution": {
                "tools_used": result.tools_used,
                "steps_taken": result.clear_metrics.steps_to_completion,
                "success": result.clear_metrics.execution_success_rate,
                "output_length": len(result.agent_output)
            },
            "performance": {
                "overall_clear_score": result.overall_clear_score,
                "passed_thresholds": result.passed_all_thresholds,
                "dimension_scores": result.dimension_scores
            },
            # ── NEW: execution-time breakdown and per-step resource attribution ──
            "time_breakdown": result.time_breakdown,
            "step_resource_profiles": result.step_resource_profiles,
            # ─────────────────────────────────────────────────────────────────────
            "recommendations": result.recommendations,
            "timestamp": timestamp
        }
        
        with open(filepath, 'w') as f:
            json.dump(result_dict, f, indent=2)
        
        print(f"   📁 Result saved: {filename}")
    
    async def _generate_mini_agent_report(self, results: List[MiniAgentEvaluationResult]):
        """Generate comprehensive Mini-Agent evaluation report"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.results_dir / f"mini_agent_clear_report_{timestamp}.md"
        
        # Calculate statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed_all_thresholds)
        avg_clear_score = sum(r.overall_clear_score for r in results) / total_tests
        avg_cost = sum(r.clear_metrics.estimated_cost_usd for r in results) / total_tests
        avg_time = sum(r.clear_metrics.total_task_time for r in results) / total_tests
        avg_steps = sum(r.clear_metrics.steps_to_completion for r in results) / total_tests
        avg_accuracy = sum(r.clear_metrics.task_completion_accuracy for r in results) / total_tests

        # Aggregate time breakdown across all results
        avg_llm_s   = sum(r.time_breakdown.get("llm_inference_s", 0)   for r in results) / total_tests
        avg_tool_s  = sum(r.time_breakdown.get("tool_execution_s", 0)  for r in results) / total_tests
        avg_coord_s = sum(r.time_breakdown.get("coordination_s", 0)    for r in results) / total_tests
        avg_llm_pct   = round(100 * avg_llm_s   / avg_time, 1) if avg_time else 0
        avg_tool_pct  = round(100 * avg_tool_s  / avg_time, 1) if avg_time else 0
        avg_coord_pct = round(100 * avg_coord_s / avg_time, 1) if avg_time else 0
        
        # Generate comprehensive report
        report = f"""# Mini-Agent CLEAR Framework Evaluation Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

This report presents comprehensive evaluation results for the Mini-Agent system using the Multi-Dimensional CLEAR Framework, specifically adapted for agent-based systems.

### 🎯 Overall Performance

| Metric | Value | Assessment |
|--------|-------|------------|
| **Success Rate** | {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%) | Overall task completion |
| **Average CLEAR Score** | {avg_clear_score:.3f}/1.000 | Multi-dimensional performance |
| **Average Cost per Task** | ${avg_cost:.3f} USD | Economic efficiency |
| **Average Task Time** | {avg_time:.1f} seconds | Execution speed |
| **Average Steps** | {avg_steps:.1f} steps | Task efficiency |
| **Average Accuracy** | {avg_accuracy:.3f}/1.000 | Output quality |

---

## 📊 CLEAR Dimension Analysis

### 💰 Cost Dimension
- **API Usage**: LLM calls and token consumption
- **Average cost per task**: ${avg_cost:.3f} USD
- **Optimization level**: {"Good" if avg_cost < 0.1 else "Needs improvement"}

### ⚡ Latency Dimension  
- **Task completion speed**: {avg_time:.1f} seconds average
- **User experience**: {"Excellent" if avg_time < 30 else "Good" if avg_time < 60 else "Slow"}

### 📈 Efficiency Dimension
- **Average steps to completion**: {avg_steps:.1f} steps
- **Resource utilization**: Memory and CPU usage
- **Tool selection effectiveness**: Appropriate tool usage

### ✅ Assurance Dimension
- **Task completion accuracy**: {avg_accuracy:.3f}/1.000
- **Output quality**: Correctness and completeness
- **Reasoning coherence**: Logical problem-solving

### 🛠️ Reliability Dimension
- **Execution stability**: Error handling and recovery
- **System consistency**: Reproducible performance

---

## 📋 Detailed Test Results

| Test Case | Category | CLEAR Score | Cost | Time | Steps | Tools | Status |
|-----------|----------|-------------|------|------|-------|-------|--------|
"""
        
        for result in results:
            status = "✅ PASS" if result.passed_all_thresholds else "❌ FAIL"
            tools_str = ", ".join(result.tools_used[:3]) + ("..." if len(result.tools_used) > 3 else "")
            
            report += f"| {result.test_case.name} | {result.test_case.category} | {result.overall_clear_score:.3f} | ${result.clear_metrics.estimated_cost_usd:.3f} | {result.clear_metrics.total_task_time:.1f}s | {result.clear_metrics.steps_to_completion} | {tools_str} | {status} |\n"

        # ── Execution Time Breakdown ──────────────────────────────────────────
        report += f"""
---

## ⏱️ Execution Time Breakdown

> Time is partitioned into three phases using timeline-weighted analysis
> (method: `{results[0].time_breakdown.get("method", "n/a") if results else "n/a"}`).
> LLM inference events are weighted 3× relative to tool calls, reflecting API round-trip latency.

### Aggregate (across all tasks)

| Phase | Avg Time (s) | Avg % of Total |
|-------|-------------|----------------|
| 🧠 LLM Inference | {avg_llm_s:.2f}s | {avg_llm_pct}% |
| 🔧 Tool Execution | {avg_tool_s:.2f}s | {avg_tool_pct}% |
| 🔄 Coordination | {avg_coord_s:.2f}s | {avg_coord_pct}% |
| **Total** | **{avg_time:.2f}s** | **100%** |

### Per-Task Breakdown

| Test Case | LLM (s) | LLM % | Tool (s) | Tool % | Coord (s) | Coord % | Total (s) |
|-----------|---------|-------|----------|--------|-----------|---------|-----------|
"""
        for result in results:
            bd = result.time_breakdown
            total = result.clear_metrics.total_task_time
            report += (
                f"| {result.test_case.name} "
                f"| {bd.get('llm_inference_s', 0):.2f} "
                f"| {bd.get('llm_inference_pct', 0)}% "
                f"| {bd.get('tool_execution_s', 0):.2f} "
                f"| {bd.get('tool_execution_pct', 0)}% "
                f"| {bd.get('coordination_s', 0):.2f} "
                f"| {bd.get('coordination_pct', 0)}% "
                f"| {total:.2f} |\n"
            )

        # ── Per-Step Resource Attribution ─────────────────────────────────────
        report += """
---

## 🔍 Per-Step Resource Attribution

Resource usage (CPU %, Memory MB) is estimated by interpolating each timeline event's
position in the log against wall-clock timestamps captured by the resource monitor.

"""
        for result in results:
            profiles = result.step_resource_profiles
            if not profiles:
                report += f"### {result.test_case.name}\n_No timeline events captured._\n\n"
                continue

            report += f"### {result.test_case.name} ({result.test_case.category})\n\n"
            report += "| # | Event Type | Time Offset (s) | CPU % | Memory (MB) |\n"
            report += "|---|------------|-----------------|-------|-------------|\n"
            for i, p in enumerate(profiles, 1):
                report += (
                    f"| {i} | {p['event_type']} "
                    f"| {p['time_offset_s']:.2f} "
                    f"| {p['cpu_percent']:.1f} "
                    f"| {p['memory_mb']:.1f} |\n"
                )
            report += "\n"

        # Add insights and recommendations
        all_recommendations = []
        for result in results:
            all_recommendations.extend(result.recommendations)
        
        # Count recommendation frequency
        rec_counts = {}
        for rec in all_recommendations:
            key = rec[:30]  # First 30 chars as key
            rec_counts[key] = rec_counts.get(key, 0) + 1
        
        report += f"""

---

## 💡 Key Insights & Recommendations

### 🔥 Most Critical Issues:
"""
        
        sorted_recs = sorted(rec_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        for rec_key, count in sorted_recs:
            full_rec = next(rec for rec in all_recommendations if rec.startswith(rec_key))
            report += f"- **({count}x)** {full_rec}\n"

        strengths: List[str] = []
        if avg_time <= 60:
            strengths.append("✅ Fast execution times")
        if avg_cost <= 0.2:
            strengths.append("✅ Cost-effective operation")
        if avg_accuracy >= 0.7:
            strengths.append("✅ High accuracy scores")
        if avg_steps <= 10:
            strengths.append("✅ Efficient step usage")

        improvements: List[str] = []
        if avg_time > 90:
            improvements.append("⚠️ Optimize execution time")
        if avg_cost > 0.3:
            improvements.append("⚠️ Reduce operational costs")
        if avg_accuracy < 0.6:
            improvements.append("⚠️ Improve task accuracy")
        if avg_steps > 15:
            improvements.append("⚠️ Optimize step efficiency")

        if not strengths:
            strengths.append("(none)")
        if not improvements:
            improvements.append("(none)")

        strengths_md = "\n".join(f"- {item}" for item in strengths)
        improvements_md = "\n".join(f"- {item}" for item in improvements)

        report += f"""

### ✅ System Strengths:
{strengths_md}

### ⚠️ Areas for Improvement:
{improvements_md}

---

## 🚀 Production Readiness

### Ready for Deployment: {"✅ YES" if passed_tests/total_tests >= 0.8 and avg_time <= 120 and avg_cost <= 0.5 else "❌ NEEDS OPTIMIZATION"}

### Next Steps:
1. {"Address identified performance issues" if passed_tests/total_tests < 0.8 else "Deploy with monitoring"}
2. {"Optimize cost and latency" if avg_cost > 0.2 or avg_time > 60 else "Scale for production load"}
3. {"Improve error handling" if any("error" in rec.lower() for rec in all_recommendations) else "Enhance monitoring"}
4. Establish production SLAs based on CLEAR metrics

---

*Report generated by Mini-Agent CLEAR Framework Evaluation System*
*Evaluation Path: {self.mini_agent_path}*
"""
        
        with open(report_path, 'w') as f:
            f.write(report)
        
        print(f"\n📊 Mini-Agent evaluation complete!")
        print(f"📄 Report: {report_path}")
        print(f"📁 Results: {self.results_dir}")
        
        # Console summary
        print("\n" + "=" * 80)
        print("MINI-AGENT CLEAR EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Success Rate: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"CLEAR Score: {avg_clear_score:.3f}/1.000")
        print(f"Avg Cost: ${avg_cost:.3f} | Avg Time: {avg_time:.1f}s | Avg Steps: {avg_steps:.1f}")
        print("=" * 80)

# Example usage
async def main():
    """Main execution function"""
    
    print("🚀 Starting Mini-Agent CLEAR Framework Evaluation")
    print("🎯 Focus: Agent-specific capabilities with proper --task integration")
    
    evaluator = MiniAgentCLEAREvaluator()
    results = await evaluator.run_comprehensive_mini_agent_evaluation()
    
    print(f"\n✅ Evaluation Complete! Tested {len(results)} scenarios")
    print("📈 Mini-Agent system assessed across all CLEAR dimensions")

if __name__ == "__main__":
    asyncio.run(main())
