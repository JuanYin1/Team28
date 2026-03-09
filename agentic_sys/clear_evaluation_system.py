#!/usr/bin/env python3
"""
Agent Comprehensive Evaluation System with CLEAR Framework
=========================================================
Implements Multi-Dimensional CLEAR Framework for pluggable agent runtimes.

This system evaluates agent capabilities:
1. Multi-step task execution and reasoning
2. Tool selection and usage effectiveness
3. Skills system integration
4. Conversation and context management
5. Error handling and recovery

CLEAR Framework dimensions:
- Cost (C): API calls, token usage, computational overhead
- Latency (L): Task completion time, tool execution delays, response speed
- Efficiency (E): Steps needed, tool selection accuracy, context utilization
- Assurance (A): Task completion accuracy, output quality, reasoning correctness
- Reliability (R): Success rates, error handling, system stability
"""

import asyncio
import argparse
import csv
import json
import time
import traceback
import tempfile
import re
import statistics
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple, Set
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
from agent_runtime.adapters import AgentAdapter, MiniAgentAdapter
from agent_runtime.factory import create_agent_adapter
from agent_runtime.models import AgentExecutionRequest
from agent_runtime.capability_probe import run_capability_probe
from agent_runtime.script_config import (
    resolve_evaluation_settings,
    resolve_script_runtime_options,
)

logger = logging.getLogger(__name__)


def _looks_like_agent_process(process_name: str, cmd_parts: List[str], process_hint: str) -> bool:
    """Best-effort matcher for arbitrary agent runtimes based on adapter hint."""
    hint = Path((process_hint or "").strip()).name.lower().replace("_", "-")
    normalized_name = Path(process_name or "").name.lower().replace("_", "-")
    normalized_parts = [
        Path(part).name.lower().replace("_", "-")
        for part in (cmd_parts or [])
        if part
    ]

    if hint:
        if len(hint) <= 3:
            if normalized_name == hint or hint in normalized_parts:
                return True
        else:
            if hint == normalized_name or hint in normalized_name or hint in normalized_parts:
                return True

    lowered_cmd = [(part or "").lower() for part in (cmd_parts or [])]
    if hint == "mini-agent":
        for idx, token in enumerate(lowered_cmd[:-1]):
            if token == "-m" and lowered_cmd[idx + 1].replace("_", "-") == "mini-agent":
                return True

    return False


@dataclass
class AgentCLEARMetrics:
    """CLEAR Framework metrics for agent evaluation."""
    
    # Cost Dimension - API and computational costs
    llm_api_calls: int = 0
    total_tokens_used: int = 0
    tool_executions: int = 0
    skill_activations: int = 0
    estimated_cost_usd: float = 0.0
    cost_is_estimated: bool = True
    context_window_usage: float = 0.0  # Percentage of context used
    
    # Latency Dimension - Time-based performance
    total_task_time: float = 0.0
    agent_thinking_time: float = 0.0
    tool_execution_time: float = 0.0
    llm_response_time: float = 0.0
    steps_to_completion: int = 0
    supports_structured_trace: bool = True
    trace_signal_quality: float = 1.0
    time_breakdown_is_estimated: bool = False
    
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
    response_consistency_measured: bool = False
    system_stability: float = 0.0

@dataclass
class AgentTestCriteria:
    """Test criteria for agent evaluation."""
    
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
class AgentTestCase:
    """Test case definition for agent evaluation."""
    
    name: str
    category: str  # "coding", "analysis", "file_operations", "reasoning", "skills_usage"
    description: str
    task_prompt: str
    evaluation_criteria: AgentTestCriteria = field(default_factory=AgentTestCriteria)
    
    # Expected outcomes
    expected_outputs: List[str] = field(default_factory=list)
    expected_file_changes: List[str] = field(default_factory=list)
    success_indicators: List[str] = field(default_factory=list)
    
    # Ground truth for comparison
    ground_truth_answer: Optional[str] = None
    core_comparable: bool = True

@dataclass
class AgentEvaluationResult:
    """Comprehensive evaluation result for agent evaluation."""
    
    test_case: AgentTestCase
    clear_metrics: AgentCLEARMetrics
    evaluation_result: EvaluationResult
    
    # Runtime execution outputs
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
    v2_dimension_scores: Dict[str, float] = field(default_factory=dict)
    v2_diagnostic_dimension_scores: Dict[str, float] = field(default_factory=dict)
    v2_dimension_details: Dict[str, Any] = field(default_factory=dict)
    failed_criteria: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    evidence_quality: Dict[str, Any] = field(default_factory=dict)
    comparability: Dict[str, Any] = field(default_factory=dict)
    gate_status: Dict[str, Any] = field(default_factory=dict)
    overall_v2_score: float = 0.0
    overall_v2_diagnostic_score: float = 0.0
    unknown_dimensions: List[str] = field(default_factory=list)
    score_coverage: float = 0.0
    is_provisional: bool = False
    repeat_stats: Dict[str, Any] = field(default_factory=dict)

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


class AgentResourceMonitor:
    """Resource monitoring for agent execution."""
    
    def __init__(self):
        self.monitoring = False
        self.start_time = 0.0
        self.peak_memory = 0.0
        self.cpu_samples = []
        self.target_process = None
        self.target_pid: Optional[int] = None
        self.process_name_hint: str = "mini-agent"
        self.monitor_thread = None
        # Timestamped snapshots: List of (abs_timestamp, memory_mb, cpu_pct)
        self.snapshots: List[Tuple[float, float, float]] = []

    def set_target_pid(self, pid: int):
        """Attach monitor to a known process PID."""
        self.target_pid = pid
        if not PSUTIL_AVAILABLE:
            return
        try:
            self.target_process = psutil.Process(pid)
            # Prime CPU accounting so subsequent samples are meaningful.
            self.target_process.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.target_process = None
        
    def start_monitoring(self, process_name_hint: str = "mini-agent"):
        """Start monitoring agent process resources"""
        self.monitoring = True
        self.start_time = time.time()
        self.peak_memory = 0.0
        self.cpu_samples = []
        self.snapshots = []
        self.target_process = None
        self.target_pid = None
        self.process_name_hint = process_name_hint or "mini-agent"
        
        def monitor_loop():
            while self.monitoring:
                try:
                    ts = time.time()
                    memory_mb = 0.0
                    cpu_pct = 0.0

                    if PSUTIL_AVAILABLE:
                        # Prefer explicit PID attachment when available.
                        if self.target_process is None and self.target_pid is not None:
                            try:
                                self.target_process = psutil.Process(self.target_pid)
                                self.target_process.cpu_percent(interval=None)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                self.target_process = None

                        # Fallback discovery by executable token.
                        if self.target_process is None:
                            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                                try:
                                    name = (proc.info.get('name') or '').lower()
                                    cmd_parts = proc.info.get('cmdline') or []
                                    if _looks_like_agent_process(name, cmd_parts, self.process_name_hint):
                                        self.target_process = psutil.Process(proc.info['pid'])
                                        self.target_process.cpu_percent(interval=None)
                                        break
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    continue

                        if self.target_process:
                            try:
                                memory_mb = self.target_process.memory_info().rss / 1024 / 1024
                                cpu_pct = self.target_process.cpu_percent()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                self.target_process = None

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

class AgentLogAnalyzer:
    """Runtime log analyzer with multiple detection methods and optional log-file access."""
    
    def __init__(
        self,
        known_tools: Optional[List[str]] = None,
        enforce_known_tools: bool = True,
        runtime_profile: str = "mini-agent",
        parser_profile: Optional[Dict[str, Any]] = None,
    ):
        profile = (runtime_profile or "").strip().lower().replace("_", "-")
        self.runtime_profile = "mini-agent" if "mini-agent" in profile else "generic"
        parser_profile = parser_profile if isinstance(parser_profile, dict) else {}

        # Multiple pattern approaches for robustness
        default_tool_call_patterns = [
            r"🔧 Tool Call: ([a-zA-Z_]+)",           # Primary pattern
            r"Tool Call: ([a-zA-Z_]+)",              # Alternative
            r'"name":\s*"([a-zA-Z_][a-zA-Z0-9_\-]*)"',             # JSON format in logs
            r'"tool(?:_name|Name)":\s*"([a-zA-Z_][a-zA-Z0-9_\-]*)"',
            r"Tool:\s*([a-zA-Z_]+)",                 # Simpler format
        ]

        default_step_patterns: List[str]
        default_thinking_patterns: List[str]
        default_assistant_patterns: List[str]
        if self.runtime_profile == "mini-agent":
            default_step_patterns = [r"Step (\d+)/\d+"]
            default_thinking_patterns = [r"🧠 Thinking:"]
            default_assistant_patterns = [r"🤖 Assistant:"]
        else:
            default_step_patterns = [r"(?:\bStep\s+(\d+)\b|\"step\"\s*:\s*(\d+))"]
            default_thinking_patterns = [r"^\s*(?:thinking|reasoning)\s*[:：]"]
            default_assistant_patterns = [r"^\s*(?:assistant|final)\s*[:：]"]

        self.tool_call_patterns = self._coerce_pattern_list(
            parser_profile.get("tool_call_patterns"),
            default_tool_call_patterns,
        )
        self.step_patterns = self._coerce_pattern_list(
            parser_profile.get("step_patterns"),
            default_step_patterns,
        )
        self.thinking_patterns = self._coerce_pattern_list(
            parser_profile.get("thinking_patterns"),
            default_thinking_patterns,
        )
        self.assistant_patterns = self._coerce_pattern_list(
            parser_profile.get("assistant_patterns"),
            default_assistant_patterns,
        )
        self.error_patterns = self._coerce_pattern_list(
            parser_profile.get("error_patterns"),
            [r"❌|✗ Error"],
        )
        self.tool_result_patterns = self._coerce_pattern_list(
            parser_profile.get("tool_result_patterns"),
            [r"(?:✓|✅)\s*Result"],
        )
        self.log_file_patterns = self._coerce_pattern_list(
            parser_profile.get("log_file_patterns"),
            [
                r"📝 Log file: (.+\.log)",
                r"(?i)log file:\s*(.+\.log)",
            ],
        )
        self.detailed_log_tool_patterns = self._coerce_pattern_list(
            parser_profile.get("detailed_log_tool_patterns"),
            [
                r'"tool_name":\s*"([a-zA-Z_][a-zA-Z0-9_\-]*)"',
                r'function":\s*{\s*"name":\s*"([a-zA-Z_][a-zA-Z0-9_\-]*)"',
            ],
        )

        # Session statistics pattern (from end of log)
        self.session_stats_pattern = str(
            parser_profile.get(
                "session_stats_pattern",
                r"Total Messages:\s*(\d+).*Tool Calls:\s*(\d+).*API Tokens Used:\s*([\d,]+)",
            )
        )

        # Timing pattern used by runtimes that print session durations.
        self.session_duration_pattern = str(
            parser_profile.get(
                "session_duration_pattern",
                r"Session Duration: (\d{2}):(\d{2}):(\d{2})",
            )
        )

        # Known tools for stricter verification when runtime semantics are compatible.
        configured_known_tools = parser_profile.get("known_tools")
        if isinstance(configured_known_tools, list):
            known_tools = [str(item) for item in configured_known_tools]
        self.known_tools = set(known_tools or [
            "read_file", "write_file", "edit_file",
            "bash", "bash_output", "bash_kill",
            "record_note", "recall_notes", "get_skill"
        ])
        configured_aliases = parser_profile.get("tool_aliases")
        self.tool_aliases: Dict[str, str] = {
            "read": "read_file",
            "write": "write_file",
            "edit": "edit_file",
            "multiedit": "edit_file",
            "bash": "bash",
            "skills": "get_skill",
            "getskill": "get_skill",
        }
        if isinstance(configured_aliases, dict):
            for alias_key, canonical in configured_aliases.items():
                alias = str(alias_key or "").strip().lower()
                canonical_name = str(canonical or "").strip().lower()
                if alias and canonical_name:
                    self.tool_aliases[alias] = canonical_name
        if "enforce_known_tools" in parser_profile:
            self.enforce_known_tools = bool(parser_profile.get("enforce_known_tools"))
        else:
            self.enforce_known_tools = enforce_known_tools

    @staticmethod
    def _coerce_pattern_list(value: Any, default: List[str]) -> List[str]:
        if value is None:
            return list(default)
        if isinstance(value, str):
            normalized = [value]
        elif isinstance(value, list):
            normalized = [str(item) for item in value if str(item).strip()]
        else:
            return list(default)
        return normalized or list(default)

    def _canonicalize_tool_name(self, raw_tool_name: str) -> str:
        candidate = str(raw_tool_name or "").strip()
        if not candidate:
            return ""
        lowered = candidate.lower()
        if lowered in self.tool_aliases:
            return self.tool_aliases[lowered]
        if lowered in self.known_tools:
            return lowered
        return candidate
    
    def analyze_execution_log(self, stdout_log: str, log_file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Enhanced log analysis with multiple detection methods and log file access
        
        Args:
            stdout_log: The stdout from runtime execution.
            log_file_path: Optional path to a runtime detailed log file.
        """
        
        analysis = {
            "total_steps": 0,
            "tools_used": [],
            "tool_call_count": 0,
            "tool_call_count_source": "none",
            "thinking_blocks": 0,
            "assistant_responses": 0,
            "errors_encountered": 0,
            "successful_operations": 0,
            "step_breakdown": [],
            "execution_timeline": [],
            "session_stats": {},
            "log_sources": ["stdout"],
            "trace_log_paths": [],
            "session_duration": {},    # Session timing from logs
            "tool_timings": [],       # List of {tool_name, estimated_duration}
            "detailed_timeline": [],    # Chronological list of all events
            "runtime_profile": self.runtime_profile,
            "has_structured_trace": False,
            "trace_signal_quality": 1.0,
        }
        
        # Analyze stdout log
        self._analyze_stdout_log(stdout_log, analysis)

        # Detect adapter-injected trace log blocks, e.g.:
        # [TRACE_LOG:/path/to/log] ... [/TRACE_LOG]
        trace_log_paths = []
        for match in re.findall(r"\[TRACE_LOG:([^\]]+)\]", stdout_log):
            path = str(match or "").strip()
            if path and path not in trace_log_paths:
                trace_log_paths.append(path)
        if trace_log_paths:
            analysis["trace_log_paths"] = trace_log_paths
            if "trace_log" not in analysis["log_sources"]:
                analysis["log_sources"].append("trace_log")
        
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
        self._finalize_tool_call_count(analysis)
        if analysis["total_steps"] <= 0 and analysis["tool_call_count"] > 0:
            # Some runtimes expose rich tool traces without explicit "step N" markers.
            analysis["total_steps"] = int(analysis["tool_call_count"])
        self._estimate_tool_timings(analysis)

        has_step_signal = analysis["total_steps"] > 0
        has_tool_signal = analysis["tool_call_count"] > 0
        has_tool_result_signal = any(
            event.get("event_type") == "tool_result"
            for event in analysis["detailed_timeline"]
        )
        analysis["has_structured_trace"] = bool(
            has_step_signal or has_tool_signal or has_tool_result_signal
        )

        if has_step_signal and has_tool_signal:
            analysis["trace_signal_quality"] = 1.0
        elif analysis["has_structured_trace"]:
            analysis["trace_signal_quality"] = 0.8
        elif stdout_log.strip():
            # Keep unstructured-output fallback neutral across runtimes.
            analysis["trace_signal_quality"] = 0.5
            analysis["assistant_responses"] = max(1, analysis["assistant_responses"])
        else:
            analysis["trace_signal_quality"] = 0.2
        
        return analysis
    
    def _analyze_stdout_log(self, log_text: str, analysis: Dict[str, Any]):
        """Analyze the stdout log text with detailed timing extraction"""
        
        lines = log_text.split('\n')
        current_step = None
        current_step_tools = []
        has_explicit_execution_lines = any("Executing tool" in line for line in lines)
        seen_stream_tool_call_ids: Set[str] = set()
        
        for i, line in enumerate(lines):
            # Track steps
            step_num: Optional[int] = None
            for step_pattern in self.step_patterns:
                step_match = re.search(step_pattern, line)
                if not step_match:
                    continue
                groups = [group for group in step_match.groups() if group]
                if groups:
                    for group in groups:
                        digits = re.findall(r"\d+", str(group))
                        if digits:
                            step_num = int(digits[0])
                            break
                else:
                    digits = re.findall(r"\d+", step_match.group(0))
                    if digits:
                        step_num = int(digits[0])
                if step_num is not None:
                    break
            if step_num is not None:
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
            is_tool_result_line = any(re.search(pattern, line) for pattern in self.tool_result_patterns)
            is_chunk_stream_tool_call = (
                "Received chunk" in line and '"tool_calls"' in line
            )
            if is_chunk_stream_tool_call:
                call_id_match = re.search(r'"id"\s*:\s*"([^"]+)"', line)
                if call_id_match:
                    call_id = call_id_match.group(1).strip()
                    if call_id in seen_stream_tool_call_ids:
                        continue
                    seen_stream_tool_call_ids.add(call_id)
                if has_explicit_execution_lines:
                    # Prefer concrete execution events over streamed delta fragments.
                    continue
            if not is_tool_result_line:
                for pattern in self.tool_call_patterns:
                    tool_match = re.search(pattern, line)
                    if tool_match:
                        tool_name = self._canonicalize_tool_name(tool_match.group(1))
                        if not tool_name:
                            continue
                        if (not self.enforce_known_tools) or (tool_name in self.known_tools):
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
            if any(re.search(pattern, line) for pattern in self.thinking_patterns):
                analysis["thinking_blocks"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "thinking",
                    "step": current_step,
                    "line": i
                })
                
            if any(re.search(pattern, line) for pattern in self.assistant_patterns):
                analysis["assistant_responses"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "assistant_response", 
                    "step": current_step,
                    "line": i
                })
            
            if any(re.search(pattern, line) for pattern in self.error_patterns):
                analysis["errors_encountered"] += 1
                analysis["detailed_timeline"].append({
                    "event_type": "error",
                    "step": current_step,
                    "line": i,
                    "text": line.strip()
                })
            
            if is_tool_result_line:
                analysis["successful_operations"] += 1
                if current_step is not None:
                    analysis["detailed_timeline"].append({
                        "event_type": "tool_result",
                        "step": current_step,
                        "line": i
                    })
        
        # Update total tool-call count before timing estimation.
        timeline_count = sum(
            1 for event in analysis["detailed_timeline"]
            if event.get("event_type") == "tool_call"
        )
        analysis["tool_call_count"] = timeline_count
        analysis["tool_call_count_source"] = "timeline" if timeline_count > 0 else "none"

        # Calculate tool-specific timing estimates
        self._estimate_tool_timings(analysis)
    
    def _estimate_tool_timings(self, analysis: Dict[str, Any]):
        """Estimate timing for each tool call based on available timing data"""
        analysis["tool_timings"] = []
        
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

    def _finalize_tool_call_count(self, analysis: Dict[str, Any]) -> None:
        """Unify tool call count across timeline, session stats, and lower-bound inference."""
        timeline_count = sum(
            1 for event in analysis["detailed_timeline"]
            if event.get("event_type") == "tool_call"
        )
        if timeline_count > 0:
            analysis["tool_call_count"] = timeline_count
            analysis["tool_call_count_source"] = "timeline"
            return

        session_tool_calls = 0
        session_stats = analysis.get("session_stats") or {}
        if isinstance(session_stats, dict):
            session_tool_calls = int(session_stats.get("tool_calls") or 0)
        if session_tool_calls > 0:
            analysis["tool_call_count"] = session_tool_calls
            analysis["tool_call_count_source"] = "session_stats"
            return

        inferred_from_tools = len(analysis.get("tools_used") or [])
        if inferred_from_tools > 0:
            analysis["tool_call_count"] = inferred_from_tools
            analysis["tool_call_count_source"] = "tools_used_lower_bound"
            return

        analysis["tool_call_count"] = 0
        analysis["tool_call_count_source"] = "none"
    
    def _analyze_detailed_log(self, log_text: str, analysis: Dict[str, Any]):
        """Analyze the detailed log file for additional information"""

        for pattern in self.detailed_log_tool_patterns:
            matches = re.findall(pattern, log_text)
            for raw_tool_name in matches:
                tool_name = self._canonicalize_tool_name(raw_tool_name)
                if not tool_name:
                    continue
                if ((not self.enforce_known_tools) or (tool_name in self.known_tools)) and tool_name not in analysis["tools_used"]:
                    analysis["tools_used"].append(tool_name)
    
    def _extract_log_file_path(self, stdout_log: str) -> Optional[str]:
        """Extract the log file path from stdout"""

        for log_pattern in self.log_file_patterns:
            match = re.search(log_pattern, stdout_log)
            if not match:
                continue
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

class AgentCLEAREvaluator:
    """
    Comprehensive agent evaluation system implementing CLEAR Framework.
    """
    
    def __init__(
        self,
        results_dir: str = "artifacts/mini-agent/phase3",
        runtime_path: Optional[str] = None,
        agent_adapter: Optional[AgentAdapter] = None,
        evaluation_settings: Optional[Dict[str, Any]] = None,
    ):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        if agent_adapter is not None:
            self.agent_adapter = agent_adapter
            self.runtime_path = runtime_path or getattr(
                agent_adapter,
                "executable",
                getattr(agent_adapter, "agent_id", "custom-agent"),
            )
        else:
            if runtime_path is not None:
                self.agent_adapter = MiniAgentAdapter(executable=runtime_path)
            else:
                self.agent_adapter = MiniAgentAdapter.auto_detect()
            self.runtime_path = getattr(self.agent_adapter, "executable", "mini-agent")
            
        # Initialize components
        self.advanced_evaluator = AdvancedEvaluator(use_llm_judge=False)
        self.resource_monitor = AgentResourceMonitor()
        self.evaluation_settings = self._normalize_evaluation_settings(evaluation_settings or {})
        self.resolved_capabilities = self._resolve_runtime_capabilities()
        self.log_analyzer = AgentLogAnalyzer(
            enforce_known_tools=bool(self.resolved_capabilities.get("tool_trace", False)),
            runtime_profile=self._agent_label(),
            parser_profile=self.evaluation_settings.get("trace_parser_profile", {}),
        )
        self.runs_per_task = max(1, int(self.evaluation_settings.get("runs_per_task", 1)))
        self.include_runtime_extension_suite = bool(
            self.evaluation_settings.get("include_runtime_extension_suite", True)
        )
        
        # Logging setup
        logging.basicConfig(level=logging.INFO)
        logger.info("Agent adapter: %s", getattr(self.agent_adapter, "agent_id", "custom-agent"))
        logger.info("Agent runtime path: %s", self.runtime_path)
        logger.info("Evaluation scoring version: %s", self.evaluation_settings.get("scoring_version", "v2"))

    def _agent_label(self) -> str:
        return getattr(self.agent_adapter, "agent_id", "agent") or "agent"

    def _artifact_prefix(self) -> str:
        return self._agent_label().replace("-", "_")

    def _default_runtime_capabilities(self) -> Dict[str, Any]:
        return {
            "structured_trace": False,
            "tool_trace": False,
            "step_trace": False,
            "timeline_events": False,
            "session_stats": False,
            "provider_cost": False,
            "token_usage": False,
            # Keep runtime extension behavior config-driven (not adapter-name-driven).
            "skills_runtime": False,
            "checker_support": {
                "file_artifacts": True,
                "stdout_capture": True,
                "exit_code": True,
                "behavior_validation": True,
            },
        }

    def _resolve_runtime_capabilities(self) -> Dict[str, Any]:
        defaults = self._default_runtime_capabilities()
        raw = self.evaluation_settings.get("resolved_capabilities", {}) or {}
        if not isinstance(raw, dict):
            raw = {}
        merged = {}
        for key, default_value in defaults.items():
            value = raw.get(key, default_value)
            if isinstance(default_value, dict):
                nested = {}
                raw_nested = value if isinstance(value, dict) else {}
                for nested_key, nested_default in default_value.items():
                    nested[nested_key] = bool(raw_nested.get(nested_key, nested_default))
                merged[key] = nested
            else:
                merged[key] = bool(value)
        return merged

    def _normalize_evaluation_settings(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize V2 settings with safe defaults."""
        defaults = {
            "scoring_version": "v2",
            "runs_per_task": 1,
            "include_runtime_extension_suite": True,
            "minimum_high_supervision_coverage": 0.40,
            "main_leaderboard_core_suite_only": True,
            "declared_capabilities": {},
            "probed_capabilities": {},
            "resolved_capabilities": {},
            "trace_parser_profile": {},
            "v2": {
                "evidence_quality": {
                    "include_in_total_score": False,
                    "provisional_if_below_high_supervision_coverage": 0.40,
                },
                "comparable_dimensions": [
                    "outcome",
                    "safety",
                    "robustness",
                    "basic_efficiency",
                ],
                "diagnostic_dimensions": [
                    "process",
                    "tool_efficiency",
                    "cost_efficiency",
                    "token_efficiency",
                    "trace_quality",
                ],
                "required_signals_for_comparable": {
                    "outcome": ["checker_executed"],
                    "safety": ["checker_executed"],
                    "robustness": ["repeated_runs"],
                    "basic_efficiency": ["wall_clock_time"],
                },
                "comparability": {
                    "hard_requirements": {"checker_must_run": True},
                    "soft_requirements": {"structured_trace_preferred": True},
                    "minimum_score_coverage_for_comparable": 1.0,
                },
                "full_comparability": {
                    "required_signals": [
                        "structured_trace",
                        "tool_trace",
                        "step_trace",
                        "timeline_events",
                    ],
                    "required_dimensions": [
                        "process",
                        "tool_efficiency",
                        "trace_quality",
                    ],
                },
                "normalization": {
                    "mode": "task_family_baseline",
                    "baseline_by_task_type": {},
                },
                "gate_caps": {"safety": 0.20, "critical": 0.45, "oracle": 0.60},
                "dimension_weights_main": {
                    "outcome": 0.45,
                    "safety": 0.20,
                    "robustness": 0.20,
                    "basic_efficiency": 0.15,
                },
                "dimension_weights_diagnostic": {
                    "process": 0.40,
                    "tool_efficiency": 0.20,
                    "cost_efficiency": 0.15,
                    "token_efficiency": 0.15,
                    "trace_quality": 0.10,
                },
                "capability_probe": {
                    "enabled": False,
                    "auto_refresh": False,
                    "profile_dir": "artifacts/capability_profiles",
                },
            },
        }

        def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
            merged = dict(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = _deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged

        normalized = _deep_merge(defaults, raw)
        normalized["minimum_high_supervision_coverage"] = max(
            0.0,
            min(1.0, float(normalized.get("minimum_high_supervision_coverage", 0.40))),
        )
        normalized["runs_per_task"] = max(1, int(normalized.get("runs_per_task", 1)))
        return normalized

    def _run_agent_with_pid_binding(self, request: AgentExecutionRequest):
        """Prefer early PID binding via callback; fall back for legacy adapters."""
        conda_mode = bool(getattr(self.agent_adapter, "conda_env", None))

        def _on_process_start(pid: int):
            self._bind_monitor_target_pid(pid, conda_mode=conda_mode)

        try:
            return self.agent_adapter.run(request, on_process_start=_on_process_start)
        except TypeError as exc:
            if "on_process_start" not in str(exc):
                raise
            execution = self.agent_adapter.run(request)
            if execution.pid is not None:
                self._bind_monitor_target_pid(execution.pid, conda_mode=conda_mode)
            return execution
    
    def create_base_test_suite(self) -> List[AgentTestCase]:
        """Create runtime-agnostic base test suite."""
        
        test_cases = []
        
        # 1. Simple File Operations
        test_cases.append(AgentTestCase(
            name="simple_file_operations",
            category="file_operations",
            description="Create, modify, and read files to test basic tool usage",
            task_prompt="""Please help me with these file operations:
1. Create a file called 'test_data.txt' with the numbers 1, 2, 3, 4, 5 (one per line)
2. Read the file back and calculate the sum of all numbers
3. Create another file called 'result.txt' with the calculated sum
4. Show me the contents of both files to confirm they were created correctly""",
            evaluation_criteria=AgentTestCriteria(
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
        test_cases.append(AgentTestCase(
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
            evaluation_criteria=AgentTestCriteria(
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
        test_cases.append(AgentTestCase(
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
            evaluation_criteria=AgentTestCriteria(
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
        test_cases.append(AgentTestCase(
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
            evaluation_criteria=AgentTestCriteria(
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
        
        return test_cases

    def create_runtime_extension_suite(self) -> List[AgentTestCase]:
        """Create runtime-specific tests; keep base suite agent-agnostic."""
        if not bool(self.resolved_capabilities.get("skills_runtime", False)):
            return []

        test_cases: List[AgentTestCase] = []

        # 5. Skills System Usage (mini-agent capability)
        test_cases.append(AgentTestCase(
            name="skills_integration_test",
            category="skills_usage",
            description="Test integration with runtime skills/tooling capabilities",
            task_prompt="""Please help me test the skills system:

1. Try to use the get_skill tool to get information about available document skills
2. Use any document-related skill to create or process a document  
3. If no document skills are available, create a simple text document and process it manually
4. Provide a summary of what skills were used and how they performed""",
            evaluation_criteria=AgentTestCriteria(
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
            ground_truth_answer="Should list available skills, demonstrate skill usage (or fallback to manual processing), and provide clear summary of skills system interaction.",
            core_comparable=False,
        ))

        return test_cases

    def create_agent_test_suite(self) -> List[AgentTestCase]:
        """Create test suite normalized for the current runtime semantics."""
        tests = self.create_base_test_suite()
        if self.include_runtime_extension_suite:
            tests += self.create_runtime_extension_suite()
        return tests
    
    async def execute_agent_task(self, test_case: AgentTestCase) -> Tuple[str, str, bool, float]:
        """
        Execute one task against the configured runtime adapter.
        Returns: (stdout, stderr, success, execution_time)
        """
        
        start_time = time.time()
        
        try:
            with tempfile.TemporaryDirectory() as temp_workspace:
                request = AgentExecutionRequest(
                    task_prompt=test_case.task_prompt,
                    workspace=temp_workspace,
                    timeout_seconds=test_case.evaluation_criteria.max_task_time_seconds,
                )
                execution = self._run_agent_with_pid_binding(request)
                logger.info(f"Executing: {' '.join(execution.command[:4])} ...")

                stdout = execution.stdout or ""
                stderr = execution.stderr or ""
                success = execution.success
                execution_time = execution.execution_time_seconds

                # Append adapter-captured trace logs (agent-agnostic) for parser visibility.
                trace_chunks = []
                if isinstance(getattr(execution, "metadata", None), dict):
                    maybe_chunks = execution.metadata.get("trace_log_chunks")
                    if isinstance(maybe_chunks, list):
                        trace_chunks = maybe_chunks
                for chunk in trace_chunks:
                    if not isinstance(chunk, dict):
                        continue
                    path = str(chunk.get("path", "")).strip()
                    text = str(chunk.get("text", "")).strip()
                    if not text:
                        continue
                    path_label = path or "unknown"
                    stdout = (
                        f"{stdout}\n[TRACE_LOG:{path_label}]\n{text}\n[/TRACE_LOG]"
                    )
                
                # Check for expected file changes in workspace
                for expected_file in test_case.expected_file_changes:
                    file_path = Path(temp_workspace) / expected_file
                    if file_path.exists():
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

        - direct mode: bind to launcher pid directly (runtime executable itself)
        - conda mode: launcher is usually `conda`; bind spawned runtime child if possible
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
                    if _looks_like_agent_process(
                        name,
                        cmd_parts,
                        getattr(self.agent_adapter, "process_name_hint", self._agent_label()),
                    ):
                        self.resource_monitor.set_target_pid(child.pid)
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            time.sleep(0.1)
    
    async def evaluate_agent_test(self, test_case: AgentTestCase) -> AgentEvaluationResult:
        """
        Comprehensive evaluation of one agent test case using CLEAR Framework.
        """
        
        logger.info(f"Evaluating agent test: {test_case.name}")
        
        # Initialize metrics
        clear_metrics = AgentCLEARMetrics()
        
        peak_memory = 0.0
        avg_cpu = 0.0
        monitor_started = False
        monitor_stopped = False

        def _stop_monitor_if_needed() -> None:
            nonlocal peak_memory, avg_cpu, monitor_stopped
            if not monitor_started or monitor_stopped:
                return
            try:
                _, peak_memory, avg_cpu = self.resource_monitor.stop_monitoring()
            finally:
                monitor_stopped = True

        try:
            # Start resource monitoring
            self.resource_monitor.start_monitoring(
                getattr(self.agent_adapter, "process_name_hint", self._agent_label())
            )
            monitor_started = True

            # Execute task and record wall-clock start for correlation.
            task_start_time = time.time()
            try:
                stdout, stderr, success, execution_time = await self.execute_agent_task(test_case)
            finally:
                _stop_monitor_if_needed()
            
            # Defensive: ensure stdout/stderr are always strings (guards against subprocess edge cases)
            stdout = stdout or ""
            stderr = stderr or ""

            # Analyze execution logs with enhanced detection
            log_analysis = self.log_analyzer.analyze_execution_log(stdout + "\n" + stderr)
            log_analysis["raw_text"] = f"{stdout}\n{stderr}"
            
            # Debug information
            logger.info(f"Log analysis results for {test_case.name}:")
            logger.info(f"  Tools detected: {log_analysis['tools_used']}")
            logger.info(f"  Tool call count: {log_analysis['tool_call_count']}")
            logger.info(f"  Session stats: {log_analysis.get('session_stats', 'Not available')}")
            logger.info(f"  Log sources: {log_analysis['log_sources']}")
            
            # Populate CLEAR metrics
            
            supports_session_stats = bool(self.resolved_capabilities.get("session_stats", False))
            supports_provider_cost = bool(self.resolved_capabilities.get("provider_cost", False))
            supports_token_usage = bool(self.resolved_capabilities.get("token_usage", False))
            supports_tool_trace = bool(self.resolved_capabilities.get("tool_trace", False))
            supports_step_trace = bool(self.resolved_capabilities.get("step_trace", False))

            # Cost Dimension - Use session stats if available, otherwise estimate
            if supports_session_stats and supports_token_usage and "session_stats" in log_analysis and "tokens_used" in log_analysis["session_stats"]:
                clear_metrics.total_tokens_used = log_analysis["session_stats"]["tokens_used"]
                clear_metrics.tool_executions = int(log_analysis["session_stats"].get("tool_calls", 0))
                clear_metrics.cost_is_estimated = not supports_provider_cost
            else:
                clear_metrics.total_tokens_used = self._estimate_token_usage(test_case.task_prompt + stdout)
                clear_metrics.tool_executions = log_analysis["tool_call_count"]
                clear_metrics.cost_is_estimated = True
            
            clear_metrics.llm_api_calls = log_analysis["thinking_blocks"] + log_analysis["total_steps"]
            if clear_metrics.llm_api_calls == 0 and (stdout.strip() or stderr.strip()):
                # For runtimes without step/thinking markers, assume at least one model turn.
                clear_metrics.llm_api_calls = max(1, log_analysis.get("assistant_responses", 0))
            clear_metrics.estimated_cost_usd = self._estimate_cost(clear_metrics.total_tokens_used, clear_metrics.llm_api_calls)
            
            # Latency Dimension
            clear_metrics.total_task_time = execution_time
            clear_metrics.steps_to_completion = log_analysis["total_steps"]
            clear_metrics.supports_structured_trace = bool(log_analysis.get("has_structured_trace"))
            clear_metrics.trace_signal_quality = float(log_analysis.get("trace_signal_quality", 1.0))

            # Compute time breakdown using timeline-weighted method (replaces hardcoded 70/30)
            time_breakdown = self._calculate_time_breakdown(log_analysis, execution_time)
            clear_metrics.time_breakdown_is_estimated = bool(time_breakdown.get("is_estimated", False))
            clear_metrics.tool_execution_time = time_breakdown["tool_execution_s"]
            clear_metrics.llm_response_time = time_breakdown["llm_inference_s"]
            clear_metrics.agent_thinking_time = time_breakdown["llm_inference_s"]  # same concept
            
            # Efficiency Dimension
            clear_metrics.memory_usage_mb = peak_memory
            clear_metrics.cpu_usage_percent = avg_cpu
            clear_metrics.steps_per_second = (
                clear_metrics.steps_to_completion / max(execution_time, 0.1)
                if clear_metrics.steps_to_completion > 0
                else 0.0
            )
            if log_analysis.get("tool_call_count", 0) > 0:
                clear_metrics.tool_selection_accuracy = self._calculate_tool_accuracy(
                    log_analysis["tools_used"],
                    test_case.evaluation_criteria.expected_tools,
                )
            else:
                clear_metrics.tool_selection_accuracy = 0.0

            if clear_metrics.supports_structured_trace and clear_metrics.steps_to_completion > 0:
                clear_metrics.task_efficiency_score = self._calculate_efficiency_score(
                    clear_metrics.steps_to_completion,
                    test_case.evaluation_criteria.max_acceptable_steps
                )
            else:
                clear_metrics.task_efficiency_score = 0.0
            
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
            clear_metrics.response_consistency = 0.0
            clear_metrics.response_consistency_measured = False
            
            # Calculate dimension scores
            dimension_scores = self._calculate_dimension_scores(clear_metrics, test_case.evaluation_criteria)
            
            # Calculate overall CLEAR score
            criteria = test_case.evaluation_criteria
            active_weights = self._get_active_dimension_weights(clear_metrics, criteria)
            overall_clear_score = sum(
                dimension_scores[dimension] * weight
                for dimension, weight in active_weights.items()
            )

            v2_scoring = self._compute_v2_scoring(
                test_case=test_case,
                stdout=stdout,
                stderr=stderr,
                clear_metrics=clear_metrics,
                evaluation_result=evaluation_result,
                log_analysis=log_analysis,
            )

            # V2 pass/fail: gate-based only. Legacy absolute thresholds remain as diagnostics.
            gate_status = v2_scoring["gate_status"]
            gate_pass = (
                gate_status.get("safety_gate", {}).get("status") == "pass"
                and gate_status.get("critical_function_gate", {}).get("status") == "pass"
                and gate_status.get("oracle_gate", {}).get("status") != "fail"
            )
            comparability = v2_scoring["comparability"]
            passed_thresholds = gate_pass
            
            # Generate recommendations
            recommendations = self._generate_recommendations(clear_metrics, test_case.evaluation_criteria)
            if v2_scoring["is_provisional"]:
                recommendations.append(
                    "📎 Provisional run - high-supervision coverage below configured threshold"
                )
            if comparability.get("status") != "COMPARABLE":
                reasons = "; ".join(comparability.get("reasons", [])) or "Comparability constraints detected"
                recommendations.append(f"🧪 Comparability: {comparability.get('status')} ({reasons})")
            if gate_status.get("critical_function_gate", {}).get("status") == "fail":
                recommendations.append("🚪 Critical function gate failed")
            if gate_status.get("safety_gate", {}).get("status") == "fail":
                recommendations.append("🚪 Safety gate failed")
            if v2_scoring.get("unknown_dimensions"):
                recommendations.append(
                    "📉 Unknown dimensions: " + ", ".join(v2_scoring["unknown_dimensions"])
                )
            
            # Per-step resource attribution
            step_resource_profiles = self._build_step_resource_profiles(
                log_analysis, task_start_time, execution_time, self.resource_monitor
            )

            # Create result
            result = AgentEvaluationResult(
                test_case=test_case,
                clear_metrics=clear_metrics,
                evaluation_result=evaluation_result,
                agent_output=stdout,
                agent_error_output=stderr,
                execution_logs=stdout + "\n--- STDERR ---\n" + stderr,
                tools_used=list(dict.fromkeys(log_analysis["tools_used"])),
                step_breakdown=log_analysis["step_breakdown"],
                overall_clear_score=v2_scoring["overall_v2_score"],
                passed_all_thresholds=passed_thresholds,
                confidence_score=evaluation_result.confidence,
                dimension_scores=dimension_scores,
                recommendations=recommendations,
                time_breakdown=time_breakdown,
                step_resource_profiles=step_resource_profiles,
                v2_dimension_scores=v2_scoring["dimension_scores"],
                v2_diagnostic_dimension_scores=v2_scoring["diagnostic_dimension_scores"],
                v2_dimension_details=v2_scoring["dimension_details"],
                overall_v2_score=v2_scoring["overall_v2_score"],
                overall_v2_diagnostic_score=v2_scoring["overall_v2_diagnostic_score"],
                unknown_dimensions=v2_scoring["unknown_dimensions"],
                score_coverage=v2_scoring["score_coverage"],
                evidence_quality=v2_scoring["evidence_quality"],
                comparability=v2_scoring["comparability"],
                gate_status=v2_scoring["gate_status"],
                is_provisional=v2_scoring["is_provisional"],
                repeat_stats={
                    "run_count": 1,
                    "pass_rate": 1.0 if passed_thresholds else 0.0,
                    "overall_v2_mean": v2_scoring["overall_v2_score"],
                    "overall_v2_diagnostic_mean": v2_scoring["overall_v2_diagnostic_score"],
                    "overall_v2_std": 0.0,
                    "overall_v2_ci95": 0.0,
                },
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Evaluation failed for {test_case.name}: {e}")
            # Return error result
            return AgentEvaluationResult(
                test_case=test_case,
                clear_metrics=AgentCLEARMetrics(),
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
        finally:
            _stop_monitor_if_needed()

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
    
    def _calculate_dimension_scores(self, metrics: AgentCLEARMetrics, 
                                             criteria: AgentTestCriteria) -> Dict[str, float]:
        """Calculate normalized CLEAR dimension scores."""
        
        scores = {}
        
        # Cost Score
        if metrics.cost_is_estimated:
            scores['cost'] = 1.0
        else:
            cost_ratio = metrics.estimated_cost_usd / criteria.max_cost_per_task
            scores['cost'] = max(0.0, 1.0 - cost_ratio)
        
        # Latency Score  
        time_ratio = metrics.total_task_time / criteria.max_task_time_seconds
        scores['latency'] = max(0.0, 1.0 - time_ratio)
        
        # Efficiency Score
        efficiency_components = [
            metrics.task_efficiency_score,
            metrics.tool_selection_accuracy,
            max(0.0, 1.0 - metrics.memory_usage_mb / 1000),  # Penalize high memory
        ]
        if metrics.supports_structured_trace:
            efficiency_components.append(min(1.0, metrics.steps_per_second * 10))  # Normalize steps per second
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
        ]
        if metrics.response_consistency_measured:
            reliability_components.append(metrics.response_consistency)
        scores['reliability'] = sum(reliability_components) / len(reliability_components)
        
        return scores

    def _get_active_dimension_weights(
        self,
        metrics: AgentCLEARMetrics,
        criteria: AgentTestCriteria,
    ) -> Dict[str, float]:
        """Re-normalize weights over dimensions that are measured with adequate confidence."""
        weights = {
            "cost": criteria.cost_weight,
            "latency": criteria.latency_weight,
            "efficiency": criteria.efficiency_weight,
            "assurance": criteria.assurance_weight,
            "reliability": criteria.reliability_weight,
        }
        if metrics.cost_is_estimated:
            weights["cost"] = 0.0
        total = sum(weights.values()) or 1.0
        return {dimension: value / total for dimension, value in weights.items()}

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _ratio_to_score(actual: float, baseline: float) -> float:
        """
        Convert "lower-is-better" ratio into [0,1] score.
        Baseline or better -> 1.0; 2x baseline -> 0.5; 3x baseline -> 0.33...
        """
        if baseline <= 0:
            return 1.0
        actual = max(actual, 0.0)
        if actual <= baseline:
            return 1.0
        return max(0.0, min(1.0, baseline / actual))

    @staticmethod
    def _score_string_matches(text: str, expected_items: List[str]) -> Optional[float]:
        if not expected_items:
            return None
        lowered = (text or "").lower()
        matches = sum(1 for item in expected_items if str(item).lower() in lowered)
        return matches / max(len(expected_items), 1)

    @staticmethod
    def _task_type_key(test_case: AgentTestCase) -> str:
        criteria_type = (test_case.evaluation_criteria.task_type or "").strip().lower()
        if criteria_type:
            return criteria_type
        category = (test_case.category or "").strip().lower()
        if category == "file_operations":
            return "file_ops"
        return category or "general"

    def _task_baseline(self, test_case: AgentTestCase) -> Dict[str, float]:
        normalization_cfg = (
            self.evaluation_settings.get("v2", {})
            .get("normalization", {})
            .get("baseline_by_task_type", {})
        )
        task_key = self._task_type_key(test_case)
        task_baseline = normalization_cfg.get(task_key) or {}
        if not isinstance(task_baseline, dict):
            task_baseline = {}

        criteria = test_case.evaluation_criteria
        return {
            "latency_seconds": float(task_baseline.get("latency_seconds", criteria.max_task_time_seconds)),
            "cost_usd": float(task_baseline.get("cost_usd", criteria.max_cost_per_task)),
            "steps": float(task_baseline.get("steps", criteria.max_acceptable_steps)),
            "memory_mb": float(task_baseline.get("memory_mb", 512.0)),
        }

    @staticmethod
    def _extract_tool_call_sequence(log_analysis: Dict[str, Any]) -> List[str]:
        sequence: List[str] = []
        for event in log_analysis.get("detailed_timeline", []):
            if event.get("event_type") != "tool_call":
                continue
            tool_name = (event.get("tool_name") or "").strip()
            if not tool_name:
                text = event.get("text") or ""
                match = re.search(r"([a-zA-Z_][a-zA-Z0-9_-]*)", text)
                if match:
                    tool_name = match.group(1)
            if tool_name:
                sequence.append(tool_name)
        return sequence

    def _checker_support_enabled(self, key: str) -> bool:
        checker_cfg = self.resolved_capabilities.get("checker_support", {})
        if not isinstance(checker_cfg, dict):
            return True
        return bool(checker_cfg.get(key, True))

    def _run_task_checker(
        self,
        *,
        test_case: AgentTestCase,
        stdout: str,
        stderr: str,
        clear_metrics: AgentCLEARMetrics,
    ) -> Dict[str, Any]:
        text = f"{stdout}\n{stderr}"
        lowered = text.lower()
        checks: Dict[str, bool] = {}

        mandatory_check_ids: List[str] = []

        expected_files = test_case.expected_file_changes or []
        if expected_files:
            for expected_file in expected_files:
                mandatory_check_ids.append(f"file_artifact:{expected_file}")
            if self._checker_support_enabled("file_artifacts"):
                for expected_file in expected_files:
                    marker = f"[FILE_CONTENT:{expected_file}]"
                    checks[f"file_artifact:{expected_file}"] = marker in stdout

        mandatory_check_ids.append("exit_code_success")
        if self._checker_support_enabled("exit_code"):
            checks["exit_code_success"] = clear_metrics.execution_success_rate >= 1.0

        expected_outputs = test_case.expected_outputs or []
        if expected_outputs:
            mandatory_check_ids.append("expected_outputs_match")
            if self._checker_support_enabled("stdout_capture"):
                exact_score = self._score_string_matches(text, expected_outputs) or 0.0
                checks["expected_outputs_match"] = exact_score >= 0.6

        behavior_checks: Dict[str, bool] = {}
        mandatory_behavior_checks: List[str] = []
        if test_case.name == "error_handling_test":
            mandatory_behavior_checks = [
                "intentional_error_triggered",
                "error_detected",
                "fix_applied",
                "rerun_succeeded",
                "final_output_verified",
            ]
        elif test_case.success_indicators:
            mandatory_behavior_checks = ["behavior_indicators_match"]
        mandatory_check_ids.extend(mandatory_behavior_checks)

        if self._checker_support_enabled("behavior_validation"):
            if test_case.name == "error_handling_test":
                behavior_checks = {
                    "intentional_error_triggered": bool(
                        re.search(r"(nonexistent\.txt|file not found|no such file)", lowered)
                    ),
                    "error_detected": bool(re.search(r"(error|syntax error|traceback)", lowered)),
                    "fix_applied": bool(re.search(r"(fix|fixed|corrected|created)", lowered)),
                    "rerun_succeeded": bool(
                        (clear_metrics.execution_success_rate >= 1.0)
                        and re.search(r"(hello world|success|fixed|correct)", lowered)
                    ),
                    "final_output_verified": bool(
                        (self._score_string_matches(text, test_case.success_indicators or []) or 0.0) >= 0.5
                    ),
                }
            elif test_case.success_indicators:
                behavior_checks = {
                    "behavior_indicators_match": bool(
                        (self._score_string_matches(text, test_case.success_indicators or []) or 0.0) >= 0.5
                    )
                }
        checks.update(behavior_checks)

        executed_checks = len(checks)
        checker_executed = executed_checks > 0
        total_possible_checks = len(mandatory_check_ids)
        pass_rate = (
            float(statistics.fmean(1.0 if value else 0.0 for value in checks.values()))
            if checker_executed
            else 0.0
        )
        checker_passed = checker_executed and all(checks.values())
        coverage = executed_checks / max(total_possible_checks, 1)

        return {
            "checker_executed": checker_executed,
            "checker_passed": checker_passed,
            "checker_score": self._clamp01(pass_rate),
            "checker_coverage": self._clamp01(coverage),
            "subchecks": checks,
            "executed_checks": executed_checks,
            "total_possible_checks": total_possible_checks,
        }

    def _dimension_detail(
        self,
        *,
        score: Optional[float],
        supported: bool,
        observed: bool,
        evidence_sources: Optional[List[str]] = None,
        missing_reasons: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_score = self._clamp01(score) if (supported and observed and score is not None) else None
        return {
            "score": normalized_score,
            "supported": bool(supported),
            "observed": bool(observed),
            "evidence_sources": list(evidence_sources or []),
            "missing_reasons": list(missing_reasons or []),
        }

    def _get_dimension_weights(self, dimensions: List[str], weight_key: str) -> Dict[str, float]:
        cfg = self.evaluation_settings.get("v2", {}).get(weight_key, {})
        if not isinstance(cfg, dict):
            cfg = {}
        weights = {dimension: max(0.0, float(cfg.get(dimension, 0.0))) for dimension in dimensions}
        if sum(weights.values()) <= 0.0:
            weights = {dimension: 1.0 for dimension in dimensions}
        return weights

    def _weighted_score_from_details(
        self,
        *,
        dimensions: List[str],
        details: Dict[str, Dict[str, Any]],
        weights: Dict[str, float],
    ) -> Tuple[float, float, Dict[str, float]]:
        total_weight = sum(max(0.0, weights.get(dimension, 0.0)) for dimension in dimensions) or 1.0
        observed_weight = 0.0
        weighted_sum = 0.0
        score_map: Dict[str, float] = {}

        for dimension in dimensions:
            weight = max(0.0, weights.get(dimension, 0.0))
            detail = details.get(dimension, {})
            score = detail.get("score")
            if score is None:
                continue
            observed_weight += weight
            weighted_sum += float(score) * weight
            score_map[dimension] = self._clamp01(float(score))

        coverage = observed_weight / total_weight if total_weight > 0 else 0.0
        if observed_weight <= 0:
            return 0.0, self._clamp01(coverage), score_map
        return self._clamp01(weighted_sum / observed_weight), self._clamp01(coverage), score_map

    def _calculate_basic_efficiency_dimension_v2(
        self,
        *,
        test_case: AgentTestCase,
        clear_metrics: AgentCLEARMetrics,
    ) -> float:
        baseline = self._task_baseline(test_case)
        return self._ratio_to_score(clear_metrics.total_task_time, baseline["latency_seconds"])

    def _calculate_process_dimension_v2(
        self,
        *,
        clear_metrics: AgentCLEARMetrics,
        log_analysis: Dict[str, Any],
        criteria: AgentTestCriteria,
    ) -> float:
        tool_seq = self._extract_tool_call_sequence(log_analysis)
        redundant_retries = 0
        longest_streak = 1
        current_streak = 1
        for idx in range(1, len(tool_seq)):
            if tool_seq[idx] == tool_seq[idx - 1]:
                redundant_retries += 1
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 1

        retry_efficiency = 1.0
        if tool_seq:
            retry_efficiency = 1.0 - (redundant_retries / len(tool_seq))
        loop_avoidance = 1.0 if longest_streak <= 2 else max(0.0, 1.0 - (longest_streak - 2) / 4.0)

        step_budget_score = 1.0
        if clear_metrics.steps_to_completion > criteria.max_acceptable_steps:
            overflow = clear_metrics.steps_to_completion - criteria.max_acceptable_steps
            step_budget_score = max(
                0.0,
                1.0 - overflow / max(criteria.max_acceptable_steps, 1),
            )

        completion_discipline = 1.0 if clear_metrics.execution_success_rate >= 1.0 else 0.2

        precondition_hits = 0
        for pattern in [r"no such file", r"command not found", r"syntax error", r"invalid argument"]:
            if re.search(pattern, (log_analysis.get("raw_text") or "").lower()):
                precondition_hits += 1
        precondition_score = max(0.0, 1.0 - (precondition_hits / 3.0))

        components = [
            self._clamp01(clear_metrics.tool_selection_accuracy),
            self._clamp01(retry_efficiency),
            self._clamp01(clear_metrics.error_recovery_effectiveness),
            self._clamp01(loop_avoidance),
            self._clamp01(step_budget_score),
            self._clamp01(completion_discipline),
            self._clamp01(precondition_score),
        ]
        return self._clamp01(sum(components) / len(components))

    def _calculate_efficiency_dimension_v2(
        self,
        *,
        test_case: AgentTestCase,
        clear_metrics: AgentCLEARMetrics,
    ) -> float:
        baseline = self._task_baseline(test_case)
        latency_score = self._ratio_to_score(clear_metrics.total_task_time, baseline["latency_seconds"])
        cost_score = self._ratio_to_score(clear_metrics.estimated_cost_usd, baseline["cost_usd"])
        if clear_metrics.cost_is_estimated:
            # Estimated cost should not over-reward; keep slightly conservative.
            cost_score = min(cost_score, 0.85)
        step_score = self._ratio_to_score(clear_metrics.steps_to_completion, baseline["steps"])
        memory_score = self._ratio_to_score(clear_metrics.memory_usage_mb, baseline["memory_mb"])

        return self._clamp01((latency_score + cost_score + step_score + memory_score) / 4.0)

    def _calculate_safety_dimension_v2(
        self,
        *,
        clear_metrics: AgentCLEARMetrics,
        log_analysis: Dict[str, Any],
        stdout: str,
        stderr: str,
    ) -> Tuple[float, int]:
        combined = f"{stdout}\n{stderr}".lower()
        policy_patterns = [
            r"permission denied",
            r"forbidden",
            r"not allowed",
            r"blocked by policy",
        ]
        policy_hits = sum(1 for pattern in policy_patterns if re.search(pattern, combined))
        error_density = log_analysis.get("errors_encountered", 0) / max(log_analysis.get("total_steps", 1), 1)

        success_component = clear_metrics.execution_success_rate
        policy_component = 0.0 if policy_hits > 0 else 1.0
        error_component = max(0.0, 1.0 - error_density)

        safety_score = (
            success_component * 0.5
            + policy_component * 0.3
            + error_component * 0.2
        )
        return self._clamp01(safety_score), policy_hits

    def _calculate_robustness_dimension_v2(
        self,
        *,
        clear_metrics: AgentCLEARMetrics,
        log_analysis: Dict[str, Any],
        run_scores: Optional[List[float]] = None,
        run_successes: Optional[List[float]] = None,
    ) -> float:
        if run_scores and len(run_scores) > 1:
            std_score = statistics.pstdev(run_scores)
            variance_stability = max(0.0, 1.0 - min(1.0, std_score * 2.0))
            success_rate = (
                sum(run_successes) / len(run_successes)
                if run_successes
                else clear_metrics.execution_success_rate
            )
            return self._clamp01(success_rate * 0.6 + variance_stability * 0.4)

        error_density = log_analysis.get("errors_encountered", 0) / max(log_analysis.get("total_steps", 1), 1)
        return self._clamp01(
            (
                clear_metrics.execution_success_rate
                + clear_metrics.system_stability
                + max(0.0, 1.0 - error_density)
            ) / 3.0
        )

    def _calculate_outcome_dimension_v2(
        self,
        *,
        test_case: AgentTestCase,
        stdout: str,
        stderr: str,
        clear_metrics: AgentCLEARMetrics,
        evaluation_result: EvaluationResult,
        checker_result: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        text = f"{stdout}\n{stderr}"
        expected_outputs = test_case.expected_outputs or []
        success_indicators = test_case.success_indicators or []

        checker_executed = bool(checker_result.get("checker_executed"))
        checker_score = float(checker_result.get("checker_score", 0.0))
        executable_score: Optional[float] = self._clamp01(checker_score) if checker_executed else None

        exact_score = self._score_string_matches(text, expected_outputs)
        soft_score = self._score_string_matches(text, success_indicators)
        llm_judge_score = (
            evaluation_result.correctness_score if self.advanced_evaluator.use_llm_judge else None
        )
        heuristic_score = self._clamp01(evaluation_result.overall_score)

        tier_scores: Dict[str, Optional[float]] = {
            "oracle/executable": executable_score,
            "exact": exact_score,
            "soft-match": soft_score,
            "llm-judge": llm_judge_score,
            "heuristic": heuristic_score,
        }

        primary_tier = "heuristic"
        outcome_score = heuristic_score
        if executable_score is not None:
            primary_tier = "oracle/executable"
            fallback = exact_score if exact_score is not None else heuristic_score
            outcome_score = self._clamp01(executable_score * 0.75 + fallback * 0.25)
        elif exact_score is not None:
            primary_tier = "exact"
            fallback = soft_score if soft_score is not None else heuristic_score
            outcome_score = self._clamp01(exact_score * 0.8 + fallback * 0.2)
        elif soft_score is not None:
            primary_tier = "soft-match"
            outcome_score = self._clamp01(soft_score * 0.8 + heuristic_score * 0.2)
        elif llm_judge_score is not None:
            primary_tier = "llm-judge"
            outcome_score = self._clamp01(llm_judge_score)

        high_supervision_available = checker_executed
        high_supervision_score = checker_score if checker_executed else 0.0

        evidence_quality = {
            "primary_tier": primary_tier,
            "tier_scores": {k: v for k, v in tier_scores.items() if v is not None},
            "high_supervision_available": high_supervision_available,
            "high_supervision_score": self._clamp01(high_supervision_score),
            "high_supervision_coverage": self._clamp01(float(checker_result.get("checker_coverage", 0.0))),
            "checker_executed": checker_executed,
            "checker_passed": bool(checker_result.get("checker_passed", False)),
            "checker_subchecks": checker_result.get("subchecks", {}),
            "include_in_total_score": bool(
                self.evaluation_settings.get("v2", {})
                .get("evidence_quality", {})
                .get("include_in_total_score", False)
            ),
        }
        return self._clamp01(outcome_score), evidence_quality

    def _apply_v2_gates(
        self,
        *,
        outcome_score: float,
        safety_score: float,
        criteria: AgentTestCriteria,
        clear_metrics: AgentCLEARMetrics,
        evidence_quality: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], float]:
        gate_caps = self.evaluation_settings.get("v2", {}).get("gate_caps", {})
        safety_cap = float(gate_caps.get("safety", 0.20))
        critical_cap = float(gate_caps.get("critical", 0.45))
        oracle_cap = float(gate_caps.get("oracle", 0.60))

        safety_pass = safety_score >= 0.7
        critical_pass = (
            clear_metrics.execution_success_rate >= 1.0
            and outcome_score >= criteria.min_accuracy_threshold
        )

        oracle_state = "not_applicable"
        if evidence_quality.get("high_supervision_available"):
            oracle_state = (
                "pass"
                if evidence_quality.get("high_supervision_score", 0.0) >= criteria.min_accuracy_threshold
                else "fail"
            )

        cap = 1.0
        if not safety_pass:
            cap = min(cap, safety_cap)
        if not critical_pass:
            cap = min(cap, critical_cap)
        if oracle_state == "fail":
            cap = min(cap, oracle_cap)

        gate_status = {
            "safety_gate": {"status": "pass" if safety_pass else "fail", "cap": safety_cap},
            "critical_function_gate": {"status": "pass" if critical_pass else "fail", "cap": critical_cap},
            "oracle_gate": {"status": oracle_state, "cap": oracle_cap},
            "final_cap": cap,
        }
        return gate_status, cap

    def _classify_comparability_v2(
        self,
        *,
        test_case: AgentTestCase,
        dimension_details: Dict[str, Dict[str, Any]],
        evidence_quality: Dict[str, Any],
        signal_values: Dict[str, bool],
        score_coverage: float,
        is_provisional: bool,
    ) -> Dict[str, Any]:
        v2_cfg = self.evaluation_settings.get("v2", {})
        comparable_dimensions = list(v2_cfg.get("comparable_dimensions", []))
        diagnostic_dimensions = list(v2_cfg.get("diagnostic_dimensions", []))
        required_signals = v2_cfg.get("required_signals_for_comparable", {})
        if not isinstance(required_signals, dict):
            required_signals = {}

        comparability_cfg = self.evaluation_settings.get("v2", {}).get("comparability", {})
        hard_requirements = comparability_cfg.get("hard_requirements", {})
        full_cfg = v2_cfg.get("full_comparability", {})
        if not isinstance(full_cfg, dict):
            full_cfg = {}

        full_required_signals = full_cfg.get(
            "required_signals",
            ["structured_trace", "tool_trace", "step_trace", "timeline_events"],
        )
        if not isinstance(full_required_signals, list):
            full_required_signals = []
        full_required_dimensions = full_cfg.get(
            "required_dimensions",
            ["process", "tool_efficiency", "trace_quality"],
        )
        if not isinstance(full_required_dimensions, list):
            full_required_dimensions = []

        def _dedupe_reasons(reasons: List[str]) -> List[str]:
            deduped: List[str] = []
            for reason in reasons:
                if reason not in deduped:
                    deduped.append(reason)
            return deduped

        def _status_from_reasons(hard: List[str], soft: List[str]) -> Tuple[str, List[str]]:
            if hard:
                return "HARD_NON_COMPARABLE", _dedupe_reasons(hard + soft)
            if soft:
                return "SOFT_NON_COMPARABLE", _dedupe_reasons(soft)
            return "COMPARABLE", []

        checker_must_run = bool(hard_requirements.get("checker_must_run", True))
        core_hard_reasons: List[str] = []
        core_soft_reasons: List[str] = []
        if checker_must_run and not bool(evidence_quality.get("checker_executed")):
            core_hard_reasons.append("No executable/exact checker evidence for this task")

        for dimension in comparable_dimensions:
            detail = dimension_details.get(dimension, {})
            if detail.get("score") is None:
                core_soft_reasons.append(f"Comparable dimension '{dimension}' is unknown or unsupported")
            for signal in required_signals.get(dimension, []) or []:
                if not bool(signal_values.get(signal, False)):
                    core_hard_reasons.append(
                        f"Comparable dimension '{dimension}' missing required signal '{signal}'"
                    )

        minimum_coverage = float(
            comparability_cfg.get("minimum_score_coverage_for_comparable", 1.0)
        )
        if score_coverage < minimum_coverage:
            core_soft_reasons.append(
                f"Score coverage {score_coverage:.2f} below required {minimum_coverage:.2f}"
            )

        if is_provisional:
            core_soft_reasons.append("Run is provisional (high-supervision coverage below threshold)")

        if not test_case.core_comparable:
            core_soft_reasons.append("Runtime-specific extension task (outside core comparable suite)")

        core_status, core_reasons = _status_from_reasons(core_hard_reasons, core_soft_reasons)

        full_hard_reasons = list(core_hard_reasons)
        full_soft_reasons = list(core_soft_reasons)
        for signal in full_required_signals:
            if not bool(signal_values.get(str(signal), False)):
                full_soft_reasons.append(
                    f"Full comparability missing required signal '{signal}'"
                )
        for dimension in full_required_dimensions:
            detail = dimension_details.get(str(dimension), {})
            if not bool(detail.get("supported", False)):
                full_soft_reasons.append(
                    f"Full comparability dimension '{dimension}' is unsupported"
                )
            elif detail.get("score") is None:
                full_soft_reasons.append(
                    f"Full comparability dimension '{dimension}' is unknown"
                )

        full_status, full_reasons = _status_from_reasons(full_hard_reasons, full_soft_reasons)

        dimension_status: Dict[str, str] = {}
        for dimension in comparable_dimensions + diagnostic_dimensions:
            detail = dimension_details.get(dimension, {})
            if not detail:
                dimension_status[dimension] = "UNKNOWN"
                continue
            if not bool(detail.get("supported", False)):
                dimension_status[dimension] = "UNSUPPORTED"
            elif detail.get("score") is None:
                dimension_status[dimension] = "UNKNOWN"
            else:
                dimension_status[dimension] = "COMPARABLE"

        eligible_for_main = core_status == "COMPARABLE"
        if self.evaluation_settings.get("main_leaderboard_core_suite_only", True) and not test_case.core_comparable:
            eligible_for_main = False
        if is_provisional:
            eligible_for_main = False
        eligible_for_full = full_status == "COMPARABLE"
        if self.evaluation_settings.get("main_leaderboard_core_suite_only", True) and not test_case.core_comparable:
            eligible_for_full = False
        if is_provisional:
            eligible_for_full = False

        return {
            "status": core_status,
            "core_status": core_status,
            "full_status": full_status,
            "reasons": core_reasons,
            "core_reasons": core_reasons,
            "full_reasons": full_reasons,
            "core_comparable": bool(test_case.core_comparable),
            "eligible_for_main_leaderboard": eligible_for_main,
            "eligible_for_full_leaderboard": eligible_for_full,
            "dimension_status": dimension_status,
            "required_signal_status": {key: bool(value) for key, value in signal_values.items()},
            "score_coverage": self._clamp01(score_coverage),
        }

    def _compute_v2_scoring(
        self,
        *,
        test_case: AgentTestCase,
        stdout: str,
        stderr: str,
        clear_metrics: AgentCLEARMetrics,
        evaluation_result: EvaluationResult,
        log_analysis: Dict[str, Any],
        run_scores: Optional[List[float]] = None,
        run_successes: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        checker_result = self._run_task_checker(
            test_case=test_case,
            stdout=stdout,
            stderr=stderr,
            clear_metrics=clear_metrics,
        )
        outcome_score, evidence_quality = self._calculate_outcome_dimension_v2(
            test_case=test_case,
            stdout=stdout,
            stderr=stderr,
            clear_metrics=clear_metrics,
            evaluation_result=evaluation_result,
            checker_result=checker_result,
        )
        process_score = self._calculate_process_dimension_v2(
            clear_metrics=clear_metrics,
            log_analysis=log_analysis,
            criteria=test_case.evaluation_criteria,
        )
        efficiency_score = self._calculate_basic_efficiency_dimension_v2(
            test_case=test_case,
            clear_metrics=clear_metrics,
        )
        robustness_score = self._calculate_robustness_dimension_v2(
            clear_metrics=clear_metrics,
            log_analysis=log_analysis,
            run_scores=run_scores,
            run_successes=run_successes,
        )
        safety_score, policy_hits = self._calculate_safety_dimension_v2(
            clear_metrics=clear_metrics,
            log_analysis=log_analysis,
            stdout=stdout,
            stderr=stderr,
        )

        baseline = self._task_baseline(test_case)
        token_baseline = max(1.0, baseline["steps"] * 300.0)
        cost_efficiency_score = self._ratio_to_score(clear_metrics.estimated_cost_usd, baseline["cost_usd"])
        token_efficiency_score = self._ratio_to_score(clear_metrics.total_tokens_used, token_baseline)
        tool_efficiency_score = self._clamp01(clear_metrics.tool_selection_accuracy)
        trace_quality_score = self._clamp01(clear_metrics.trace_signal_quality)

        supports_structured_trace = bool(self.resolved_capabilities.get("structured_trace", False))
        supports_tool_trace = bool(self.resolved_capabilities.get("tool_trace", False))
        supports_step_trace = bool(self.resolved_capabilities.get("step_trace", False))
        supports_provider_cost = bool(self.resolved_capabilities.get("provider_cost", False))
        supports_token_usage = bool(self.resolved_capabilities.get("token_usage", False))
        has_session_stats = bool(log_analysis.get("session_stats", {}))
        has_token_signal = bool(log_analysis.get("session_stats", {}).get("tokens_used"))
        has_tool_signal = bool(log_analysis.get("tool_call_count", 0) > 0)
        has_step_signal = bool(log_analysis.get("total_steps", 0) > 0)
        has_timeline_signal = bool(log_analysis.get("detailed_timeline"))
        observed_structured_trace = bool(
            clear_metrics.supports_structured_trace or has_tool_signal or has_step_signal or has_timeline_signal
        )
        observed_tool_trace = bool(has_tool_signal)
        observed_step_trace = bool(has_step_signal)
        supports_process = bool(
            (supports_structured_trace and supports_tool_trace and supports_step_trace)
            or (observed_structured_trace and observed_tool_trace and observed_step_trace)
        )
        observes_process = bool(supports_process and observed_structured_trace and observed_tool_trace and observed_step_trace)
        supports_tool_efficiency = bool(
            test_case.evaluation_criteria.expected_tools and (supports_tool_trace or observed_tool_trace)
        )
        supports_trace_quality = bool(supports_structured_trace or observed_structured_trace)

        dimension_details: Dict[str, Dict[str, Any]] = {
            "outcome": self._dimension_detail(
                score=outcome_score if evidence_quality.get("checker_executed") else None,
                supported=True,
                observed=bool(evidence_quality.get("checker_executed")),
                evidence_sources=["checker"],
                missing_reasons=[] if evidence_quality.get("checker_executed") else ["checker_not_executed"],
            ),
            "safety": self._dimension_detail(
                score=safety_score,
                supported=True,
                observed=True,
                evidence_sources=["stdout", "stderr", "checker"],
            ),
            "robustness": self._dimension_detail(
                score=robustness_score,
                supported=True,
                observed=True,
                evidence_sources=["repeated_runs" if (run_scores and len(run_scores) > 1) else "single_run_proxy"],
            ),
            "basic_efficiency": self._dimension_detail(
                score=efficiency_score,
                supported=True,
                observed=True,
                evidence_sources=["wall_clock_time"],
            ),
            "process": self._dimension_detail(
                score=process_score,
                supported=supports_process,
                observed=observes_process,
                evidence_sources=["structured_trace", "timeline"],
                missing_reasons=(
                    []
                    if observes_process
                    else ["trace_or_step_or_tool_signal_missing"]
                ),
            ),
            "tool_efficiency": self._dimension_detail(
                score=tool_efficiency_score,
                supported=supports_tool_efficiency,
                observed=supports_tool_efficiency and observed_tool_trace,
                evidence_sources=["tool_trace"],
                missing_reasons=[] if (supports_tool_efficiency and observed_tool_trace) else ["tool_trace_unavailable"],
            ),
            "cost_efficiency": self._dimension_detail(
                score=cost_efficiency_score,
                supported=supports_provider_cost,
                observed=supports_provider_cost and (not clear_metrics.cost_is_estimated),
                evidence_sources=["provider_cost"],
                missing_reasons=[] if (supports_provider_cost and (not clear_metrics.cost_is_estimated)) else ["provider_cost_unavailable"],
            ),
            "token_efficiency": self._dimension_detail(
                score=token_efficiency_score,
                supported=supports_token_usage,
                observed=supports_token_usage and has_token_signal,
                evidence_sources=["session_stats_tokens"],
                missing_reasons=[] if (supports_token_usage and has_token_signal) else ["token_usage_unavailable"],
            ),
            "trace_quality": self._dimension_detail(
                score=trace_quality_score,
                supported=supports_trace_quality,
                observed=supports_trace_quality and observed_structured_trace,
                evidence_sources=["trace_signal"],
                missing_reasons=[] if (supports_trace_quality and observed_structured_trace) else ["structured_trace_unavailable"],
            ),
        }

        v2_cfg = self.evaluation_settings.get("v2", {})
        comparable_dimensions = list(v2_cfg.get("comparable_dimensions", []))
        diagnostic_dimensions = list(v2_cfg.get("diagnostic_dimensions", []))

        for dimension in comparable_dimensions + diagnostic_dimensions:
            if dimension in dimension_details:
                continue
            dimension_details[dimension] = self._dimension_detail(
                score=None,
                supported=False,
                observed=False,
                missing_reasons=["dimension_not_implemented"],
            )

        main_weights = self._get_dimension_weights(comparable_dimensions, "dimension_weights_main")
        diagnostic_weights = self._get_dimension_weights(diagnostic_dimensions, "dimension_weights_diagnostic")
        raw_score, score_coverage, main_scores = self._weighted_score_from_details(
            dimensions=comparable_dimensions,
            details=dimension_details,
            weights=main_weights,
        )
        diagnostic_score, _, diagnostic_scores = self._weighted_score_from_details(
            dimensions=diagnostic_dimensions,
            details=dimension_details,
            weights=diagnostic_weights,
        )
        unknown_dimensions = sorted(
            dimension
            for dimension, detail in dimension_details.items()
            if detail.get("score") is None
        )

        gate_status, cap = self._apply_v2_gates(
            outcome_score=outcome_score,
            safety_score=safety_score,
            criteria=test_case.evaluation_criteria,
            clear_metrics=clear_metrics,
            evidence_quality=evidence_quality,
        )
        final_score = min(raw_score, cap)

        evidence_cfg = self.evaluation_settings.get("v2", {}).get("evidence_quality", {})
        provisional_threshold = float(
            evidence_cfg.get(
                "provisional_if_below_high_supervision_coverage",
                self.evaluation_settings.get("minimum_high_supervision_coverage", 0.4),
            )
        )
        is_provisional = evidence_quality.get("high_supervision_coverage", 0.0) < provisional_threshold

        signal_values = {
            "checker_executed": bool(evidence_quality.get("checker_executed")),
            "repeated_runs": bool((run_scores and len(run_scores) > 1) or self.runs_per_task > 1),
            "wall_clock_time": clear_metrics.total_task_time >= 0.0,
            "structured_trace": observed_structured_trace,
            "tool_trace": observed_tool_trace,
            "step_trace": observed_step_trace,
            "timeline_events": has_timeline_signal,
            "session_stats": has_session_stats,
            "provider_cost": bool(supports_provider_cost and (not clear_metrics.cost_is_estimated)),
            "token_usage": has_token_signal,
        }

        comparability = self._classify_comparability_v2(
            test_case=test_case,
            dimension_details=dimension_details,
            evidence_quality=evidence_quality,
            signal_values=signal_values,
            score_coverage=score_coverage,
            is_provisional=is_provisional,
        )

        evidence_quality["policy_hits"] = policy_hits
        evidence_quality["provisional_threshold"] = provisional_threshold
        evidence_quality["evidence_quality_in_total"] = False
        gate_status["raw_score_before_gate"] = self._clamp01(raw_score)

        return {
            "dimension_scores": main_scores,
            "diagnostic_dimension_scores": diagnostic_scores,
            "dimension_details": dimension_details,
            "overall_v2_score": self._clamp01(final_score),
            "overall_v2_diagnostic_score": self._clamp01(diagnostic_score),
            "unknown_dimensions": unknown_dimensions,
            "score_coverage": self._clamp01(score_coverage),
            "evidence_quality": evidence_quality,
            "comparability": comparability,
            "gate_status": gate_status,
            "is_provisional": is_provisional,
        }
    
    def _generate_recommendations(self, metrics: AgentCLEARMetrics, 
                                           criteria: AgentTestCriteria) -> List[str]:
        """Generate optimization recommendations from CLEAR metrics."""
        
        recommendations = []
        
        # Cost recommendations
        if (not metrics.cost_is_estimated) and metrics.estimated_cost_usd > criteria.max_cost_per_task * 0.8:
            recommendations.append(f"💰 Optimize token usage - cost ${metrics.estimated_cost_usd:.3f} approaching limit ${criteria.max_cost_per_task:.3f}")
        
        # Latency recommendations
        if metrics.total_task_time > criteria.max_task_time_seconds * 0.7:
            recommendations.append(f"⚡ Task taking too long - {metrics.total_task_time:.1f}s vs {criteria.max_task_time_seconds}s limit")
        
        if metrics.steps_to_completion > criteria.max_acceptable_steps:
            recommendations.append(f"🔄 Too many steps - {metrics.steps_to_completion} vs {criteria.max_acceptable_steps} max")
        
        # Efficiency recommendations
        if metrics.tool_selection_accuracy < 0.7:
            recommendations.append(f"🔧 Improve tool selection - accuracy {metrics.tool_selection_accuracy:.2f}")
        
        if metrics.supports_structured_trace and metrics.task_efficiency_score < 0.6:
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

        if metrics.cost_is_estimated:
            recommendations.append("💲 Cost is estimated (not provider-reported) and excluded from strict scoring")

        if not metrics.supports_structured_trace:
            recommendations.append("🧾 Limited runtime trace - step-level efficiency metrics are approximated")
        
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
            if not log_analysis.get("has_structured_trace", False):
                llm_s = round(execution_time, 2)
                tool_s = 0.0
                coord_s = 0.0
                method = "coarse_no_structured_trace"
                llm_pct, tool_pct, coord_pct = (100.0, 0.0, 0.0) if execution_time else (0.0, 0.0, 0.0)
            else:
                llm_s = round(execution_time * 0.70, 2)
                tool_s = round(execution_time * 0.20, 2)
                coord_s = round(execution_time * 0.10, 2)
                method = "fixed_estimate (no timeline)"
                llm_pct, tool_pct, coord_pct = 70.0, 20.0, 10.0
            return {
                "llm_inference_s": llm_s,
                "tool_execution_s": tool_s,
                "coordination_s": coord_s,
                "llm_inference_pct": llm_pct,
                "tool_execution_pct": tool_pct,
                "coordination_pct": coord_pct,
                "method": method,
                "is_estimated": True,
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
            "is_estimated": True,
            "llm_events": sum(1 for e in timeline if e["event_type"] in LLM_TYPES),
            "tool_events": sum(1 for e in timeline if e["event_type"] in TOOL_TYPES),
            "coord_events": sum(1 for e in timeline if e["event_type"] not in LLM_TYPES | TOOL_TYPES),
        }

    def _build_step_resource_profiles(
        self,
        log_analysis: Dict[str, Any],
        task_start_time: float,
        execution_time: float,
        resource_monitor: "AgentResourceMonitor",
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

    def _aggregate_repeated_results(
        self,
        test_case: AgentTestCase,
        run_results: List[AgentEvaluationResult],
    ) -> AgentEvaluationResult:
        """Aggregate repeated runs into one comparable result."""
        if not run_results:
            raise ValueError("run_results cannot be empty")
        if len(run_results) == 1:
            return run_results[0]

        primary = run_results[0]
        run_count = len(run_results)
        run_passes = [1.0 if r.passed_all_thresholds else 0.0 for r in run_results]
        pass_rate = sum(run_passes) / run_count

        v2_scores = [r.overall_v2_score or r.overall_clear_score for r in run_results]
        diag_scores = [r.overall_v2_diagnostic_score for r in run_results]
        mean_v2 = statistics.fmean(v2_scores)
        std_v2 = statistics.pstdev(v2_scores) if run_count > 1 else 0.0
        ci95_v2 = 1.96 * std_v2 / (run_count ** 0.5) if run_count > 1 else 0.0
        mean_diag = statistics.fmean(diag_scores)
        std_diag = statistics.pstdev(diag_scores) if run_count > 1 else 0.0
        ci95_diag = 1.96 * std_diag / (run_count ** 0.5) if run_count > 1 else 0.0

        eval_overalls = [r.evaluation_result.overall_score for r in run_results]
        eval_conf = [r.evaluation_result.confidence for r in run_results]

        def _mean_metric(getter, default: float = 0.0) -> float:
            vals = [getter(r) for r in run_results]
            if not vals:
                return default
            return float(statistics.fmean(vals))

        cm = primary.clear_metrics
        cm.total_task_time = _mean_metric(lambda r: r.clear_metrics.total_task_time)
        cm.estimated_cost_usd = _mean_metric(lambda r: r.clear_metrics.estimated_cost_usd)
        cm.steps_to_completion = int(round(_mean_metric(lambda r: r.clear_metrics.steps_to_completion)))
        cm.execution_success_rate = pass_rate
        cm.task_completion_accuracy = _mean_metric(lambda r: r.clear_metrics.task_completion_accuracy)
        cm.output_quality_score = _mean_metric(lambda r: r.clear_metrics.output_quality_score)
        cm.reasoning_coherence = _mean_metric(lambda r: r.clear_metrics.reasoning_coherence)
        cm.tool_selection_accuracy = _mean_metric(lambda r: r.clear_metrics.tool_selection_accuracy)
        cm.task_efficiency_score = _mean_metric(lambda r: r.clear_metrics.task_efficiency_score)
        cm.error_recovery_effectiveness = _mean_metric(lambda r: r.clear_metrics.error_recovery_effectiveness)
        cm.system_stability = _mean_metric(lambda r: r.clear_metrics.system_stability)
        cm.memory_usage_mb = _mean_metric(lambda r: r.clear_metrics.memory_usage_mb)
        cm.cpu_usage_percent = _mean_metric(lambda r: r.clear_metrics.cpu_usage_percent)
        cm.steps_per_second = _mean_metric(lambda r: r.clear_metrics.steps_per_second)
        cm.trace_signal_quality = _mean_metric(lambda r: r.clear_metrics.trace_signal_quality, default=0.0)
        cm.cost_is_estimated = all(r.clear_metrics.cost_is_estimated for r in run_results)
        cm.supports_structured_trace = any(r.clear_metrics.supports_structured_trace for r in run_results)
        cm.time_breakdown_is_estimated = all(r.clear_metrics.time_breakdown_is_estimated for r in run_results)

        dim_keys = set().union(*(r.dimension_scores.keys() for r in run_results))
        primary.dimension_scores = {
            key: _mean_metric(lambda r, k=key: r.dimension_scores.get(k, 0.0))
            for key in dim_keys
        }

        v2_cfg = self.evaluation_settings.get("v2", {})
        comparable_dimensions = list(v2_cfg.get("comparable_dimensions", []))
        diagnostic_dimensions = list(v2_cfg.get("diagnostic_dimensions", []))
        main_weights = self._get_dimension_weights(comparable_dimensions, "dimension_weights_main")
        diagnostic_weights = self._get_dimension_weights(diagnostic_dimensions, "dimension_weights_diagnostic")

        all_dimensions = set(comparable_dimensions + diagnostic_dimensions)
        for result in run_results:
            all_dimensions.update(result.v2_dimension_details.keys())

        aggregated_details: Dict[str, Dict[str, Any]] = {}
        for dimension in sorted(all_dimensions):
            dimension_run_details = [r.v2_dimension_details.get(dimension, {}) for r in run_results]
            observed_scores = [
                float(detail.get("score"))
                for detail in dimension_run_details
                if detail.get("score") is not None
            ]
            supported = any(bool(detail.get("supported", False)) for detail in dimension_run_details)
            evidence_sources: List[str] = []
            missing_reasons: List[str] = []
            for detail in dimension_run_details:
                for source in detail.get("evidence_sources", []) or []:
                    if source not in evidence_sources:
                        evidence_sources.append(source)
                for reason in detail.get("missing_reasons", []) or []:
                    if reason not in missing_reasons:
                        missing_reasons.append(reason)

            agg_score: Optional[float] = None
            if observed_scores:
                agg_score = self._clamp01(float(statistics.fmean(observed_scores)))

            aggregated_details[dimension] = self._dimension_detail(
                score=agg_score,
                supported=supported,
                observed=agg_score is not None,
                evidence_sources=evidence_sources,
                missing_reasons=missing_reasons or (["no_observed_signal"] if agg_score is None else []),
            )

        variability = max(0.0, 1.0 - min(1.0, std_v2 * 2.0))
        aggregated_robustness = self._clamp01(pass_rate * 0.6 + variability * 0.4)
        if "robustness" in aggregated_details:
            detail = aggregated_details["robustness"]
            if detail.get("score") is not None:
                detail["score"] = aggregated_robustness
                detail["observed"] = True

        raw_v2, score_coverage, main_scores = self._weighted_score_from_details(
            dimensions=comparable_dimensions,
            details=aggregated_details,
            weights=main_weights,
        )
        raw_diag, _, diagnostic_scores_map = self._weighted_score_from_details(
            dimensions=diagnostic_dimensions,
            details=aggregated_details,
            weights=diagnostic_weights,
        )
        unknown_dimensions = sorted(
            dimension for dimension, detail in aggregated_details.items() if detail.get("score") is None
        )

        gate_caps = self.evaluation_settings.get("v2", {}).get("gate_caps", {})
        safety_cap = float(gate_caps.get("safety", 0.20))
        critical_cap = float(gate_caps.get("critical", 0.45))
        oracle_cap = float(gate_caps.get("oracle", 0.60))

        safety_fail = any(r.gate_status.get("safety_gate", {}).get("status") == "fail" for r in run_results)
        critical_fail = any(r.gate_status.get("critical_function_gate", {}).get("status") == "fail" for r in run_results)
        oracle_fail = any(r.gate_status.get("oracle_gate", {}).get("status") == "fail" for r in run_results)

        final_cap = 1.0
        if safety_fail:
            final_cap = min(final_cap, safety_cap)
        if critical_fail:
            final_cap = min(final_cap, critical_cap)
        if oracle_fail:
            final_cap = min(final_cap, oracle_cap)

        primary.gate_status = {
            "safety_gate": {"status": "fail" if safety_fail else "pass", "cap": safety_cap},
            "critical_function_gate": {"status": "fail" if critical_fail else "pass", "cap": critical_cap},
            "oracle_gate": {"status": "fail" if oracle_fail else "pass", "cap": oracle_cap},
            "final_cap": final_cap,
            "raw_score_before_gate": self._clamp01(raw_v2),
            "aggregated_over_runs": run_count,
        }

        def _worst_status(statuses: List[str]) -> str:
            if "HARD_NON_COMPARABLE" in statuses:
                return "HARD_NON_COMPARABLE"
            if "SOFT_NON_COMPARABLE" in statuses:
                return "SOFT_NON_COMPARABLE"
            return "COMPARABLE"

        core_statuses = [
            r.comparability.get("core_status", r.comparability.get("status", "COMPARABLE"))
            for r in run_results
        ]
        full_statuses = [
            r.comparability.get("full_status", r.comparability.get("status", "COMPARABLE"))
            for r in run_results
        ]
        core_status = _worst_status(core_statuses)
        full_status = _worst_status(full_statuses)

        core_reasons: List[str] = []
        full_reasons: List[str] = []
        for result in run_results:
            for reason in result.comparability.get("core_reasons", result.comparability.get("reasons", [])) or []:
                if reason not in core_reasons:
                    core_reasons.append(reason)
            for reason in result.comparability.get("full_reasons", result.comparability.get("reasons", [])) or []:
                if reason not in full_reasons:
                    full_reasons.append(reason)

        dimension_status: Dict[str, str] = {}
        for dimension in sorted(all_dimensions):
            detail = aggregated_details.get(dimension, {})
            if not bool(detail.get("supported", False)):
                dimension_status[dimension] = "UNSUPPORTED"
            elif detail.get("score") is None:
                dimension_status[dimension] = "UNKNOWN"
            else:
                dimension_status[dimension] = "COMPARABLE"

        required_signal_keys = set()
        for result in run_results:
            required_signal_keys.update((result.comparability.get("required_signal_status") or {}).keys())
        required_signal_status = {
            key: all(bool((result.comparability.get("required_signal_status") or {}).get(key, False)) for result in run_results)
            for key in sorted(required_signal_keys)
        }

        high_coverage_mean = _mean_metric(
            lambda r: r.evidence_quality.get("high_supervision_coverage", 0.0)
        )
        provisional_threshold = float(
            self.evaluation_settings.get("v2", {})
            .get("evidence_quality", {})
            .get(
                "provisional_if_below_high_supervision_coverage",
                self.evaluation_settings.get("minimum_high_supervision_coverage", 0.4),
            )
        )
        primary.is_provisional = high_coverage_mean < provisional_threshold

        if primary.is_provisional and core_status == "COMPARABLE":
            core_status = "SOFT_NON_COMPARABLE"
            if "Run is provisional (high-supervision coverage below threshold)" not in core_reasons:
                core_reasons.append("Run is provisional (high-supervision coverage below threshold)")
        if primary.is_provisional and full_status == "COMPARABLE":
            full_status = "SOFT_NON_COMPARABLE"
            if "Run is provisional (high-supervision coverage below threshold)" not in full_reasons:
                full_reasons.append("Run is provisional (high-supervision coverage below threshold)")

        eligible_for_main = (
            core_status == "COMPARABLE"
            and (not primary.is_provisional)
            and (
                (not self.evaluation_settings.get("main_leaderboard_core_suite_only", True))
                or test_case.core_comparable
            )
        )
        eligible_for_full = (
            full_status == "COMPARABLE"
            and (not primary.is_provisional)
            and (
                (not self.evaluation_settings.get("main_leaderboard_core_suite_only", True))
                or test_case.core_comparable
            )
        )

        primary.comparability = {
            "status": core_status,
            "core_status": core_status,
            "full_status": full_status,
            "reasons": core_reasons,
            "core_reasons": core_reasons,
            "full_reasons": full_reasons,
            "core_comparable": bool(test_case.core_comparable),
            "eligible_for_main_leaderboard": eligible_for_main,
            "eligible_for_full_leaderboard": eligible_for_full,
            "dimension_status": dimension_status,
            "required_signal_status": required_signal_status,
            "score_coverage": self._clamp01(score_coverage),
        }

        primary_tiers = [r.evidence_quality.get("primary_tier", "heuristic") for r in run_results]
        tier_scores: Dict[str, float] = {}
        tier_keys = set().union(
            *[set((r.evidence_quality.get("tier_scores") or {}).keys()) for r in run_results]
        )
        for key in tier_keys:
            vals = [
                float((r.evidence_quality.get("tier_scores") or {}).get(key, 0.0))
                for r in run_results
                if key in (r.evidence_quality.get("tier_scores") or {})
            ]
            if vals:
                tier_scores[key] = float(statistics.fmean(vals))

        primary.evidence_quality = {
            "primary_tier": primary_tiers[0] if len(set(primary_tiers)) == 1 else "mixed",
            "tier_scores": tier_scores,
            "high_supervision_available": high_coverage_mean > 0.0,
            "high_supervision_coverage": self._clamp01(high_coverage_mean),
            "checker_executed": any(bool(r.evidence_quality.get("checker_executed")) for r in run_results),
            "checker_passed": all(bool(r.evidence_quality.get("checker_passed", False)) for r in run_results),
            "include_in_total_score": False,
            "evidence_quality_in_total": False,
            "provisional_threshold": provisional_threshold,
            "aggregated_over_runs": run_count,
        }

        primary.v2_dimension_details = aggregated_details
        primary.v2_dimension_scores = main_scores
        primary.v2_diagnostic_dimension_scores = diagnostic_scores_map
        primary.score_coverage = self._clamp01(score_coverage)
        primary.unknown_dimensions = unknown_dimensions
        primary.overall_v2_score = self._clamp01(min(raw_v2, final_cap))
        primary.overall_v2_diagnostic_score = self._clamp01(raw_diag)
        primary.overall_clear_score = primary.overall_v2_score

        gate_pass = (
            primary.gate_status["safety_gate"]["status"] == "pass"
            and primary.gate_status["critical_function_gate"]["status"] == "pass"
            and primary.gate_status["oracle_gate"]["status"] != "fail"
        )
        primary.passed_all_thresholds = pass_rate >= 0.67 and gate_pass

        primary.repeat_stats = {
            "run_count": run_count,
            "pass_rate": pass_rate,
            "overall_v2_mean": mean_v2,
            "overall_v2_std": std_v2,
            "overall_v2_ci95": ci95_v2,
            "overall_v2_diagnostic_mean": mean_diag,
            "overall_v2_diagnostic_std": std_diag,
            "overall_v2_diagnostic_ci95": ci95_diag,
            "run_scores": v2_scores,
            "run_diagnostic_scores": diag_scores,
        }

        primary.confidence_score = float(statistics.fmean(eval_conf)) if eval_conf else primary.confidence_score
        primary.evaluation_result.overall_score = float(statistics.fmean(eval_overalls)) if eval_overalls else primary.evaluation_result.overall_score
        primary.evaluation_result.correctness_score = _mean_metric(lambda r: r.evaluation_result.correctness_score)
        primary.evaluation_result.completeness_score = _mean_metric(lambda r: r.evaluation_result.completeness_score)
        primary.evaluation_result.reasoning_score = _mean_metric(lambda r: r.evaluation_result.reasoning_score)
        primary.evaluation_result.efficiency_score = _mean_metric(lambda r: r.evaluation_result.efficiency_score)
        primary.evaluation_result.execution_score = _mean_metric(lambda r: r.evaluation_result.execution_score)
        primary.evaluation_result.confidence = primary.confidence_score
        primary.evaluation_result.passed = primary.passed_all_thresholds

        dedup_tools: List[str] = []
        for result in run_results:
            for tool in result.tools_used:
                if tool not in dedup_tools:
                    dedup_tools.append(tool)
        primary.tools_used = dedup_tools

        dedup_recommendations: List[str] = []
        for result in run_results:
            for recommendation in result.recommendations:
                if recommendation not in dedup_recommendations:
                    dedup_recommendations.append(recommendation)
        primary.recommendations = dedup_recommendations

        primary.time_breakdown = {
            "llm_inference_s": _mean_metric(lambda r: r.time_breakdown.get("llm_inference_s", 0.0)),
            "tool_execution_s": _mean_metric(lambda r: r.time_breakdown.get("tool_execution_s", 0.0)),
            "coordination_s": _mean_metric(lambda r: r.time_breakdown.get("coordination_s", 0.0)),
            "method": "multi_run_mean",
            "is_estimated": True,
        }
        total_time = max(primary.clear_metrics.total_task_time, 1e-6)
        primary.time_breakdown["llm_inference_pct"] = round(
            100.0 * primary.time_breakdown["llm_inference_s"] / total_time, 1
        )
        primary.time_breakdown["tool_execution_pct"] = round(
            100.0 * primary.time_breakdown["tool_execution_s"] / total_time, 1
        )
        primary.time_breakdown["coordination_pct"] = round(
            100.0 * primary.time_breakdown["coordination_s"] / total_time, 1
        )

        return primary

    async def run_comprehensive_evaluation(self) -> List[AgentEvaluationResult]:
        """Run comprehensive agent evaluation with CLEAR Framework."""
        
        print(f"🤖 Agent Comprehensive Evaluation with CLEAR Framework ({self._agent_label()})")
        print("=" * 80)
        print("Evaluating agent system across 5 key dimensions:")
        print("💰 Cost | ⚡ Latency | 📈 Efficiency | ✅ Assurance | 🛠️ Reliability")
        print("=" * 80)
        
        test_cases = self.create_agent_test_suite()
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[{i}/{len(test_cases)}] Testing: {test_case.name} ({test_case.category})")
            print(f"📋 {test_case.description}")
            if test_case.evaluation_criteria.expected_tools:
                print(f"🎯 Expected tools: {test_case.evaluation_criteria.expected_tools}")
            else:
                print("🎯 Expected tools: (runtime-agnostic mode)")
            
            run_results: List[AgentEvaluationResult] = []
            for run_idx in range(self.runs_per_task):
                if self.runs_per_task > 1:
                    print(f"   ↻ Run {run_idx + 1}/{self.runs_per_task}")
                run_results.append(await self.evaluate_agent_test(test_case))

            result = self._aggregate_repeated_results(test_case, run_results)
            results.append(result)
            
            # Print immediate summary
            status = "✅ PASS" if result.passed_all_thresholds else "❌ FAIL"
            print(f"   {status} | CLEAR Score: {result.overall_clear_score:.3f} | Confidence: {result.confidence_score:.3f}")
            if self.runs_per_task > 1:
                print(
                    f"   📐 mean={result.repeat_stats.get('overall_v2_mean', 0.0):.3f} "
                    f"std={result.repeat_stats.get('overall_v2_std', 0.0):.3f} "
                    f"CI95=±{result.repeat_stats.get('overall_v2_ci95', 0.0):.3f}"
                )
            print(f"   💰 ${result.clear_metrics.estimated_cost_usd:.3f} | ⚡ {result.clear_metrics.total_task_time:.1f}s | 🔧 {len(result.tools_used)} tools | 🔄 {result.clear_metrics.steps_to_completion} steps")
            
            # Save result
            await self._save_result(result)
        
        # Generate comprehensive report
        await self._generate_report(results)
        
        return results

    async def _save_result(self, result: AgentEvaluationResult):
        """Save detailed agent evaluation result."""
        
        timestamp = int(time.time())
        filename = f"{self._artifact_prefix()}_{result.test_case.name}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        result_dict = {
            "schema_version": "phase3.v3",
            "test_case": {
                "name": result.test_case.name,
                "category": result.test_case.category,
                "description": result.test_case.description,
                "task_prompt": result.test_case.task_prompt,
                "core_comparable": result.test_case.core_comparable,
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
                "overall_v2_score": result.overall_v2_score,
                "overall_v2_diagnostic_score": result.overall_v2_diagnostic_score,
                "passed_thresholds": result.passed_all_thresholds,
                "dimension_scores": result.dimension_scores,
                "v2_dimension_scores": result.v2_dimension_scores,
                "v2_diagnostic_dimension_scores": result.v2_diagnostic_dimension_scores,
                "v2_dimension_details": result.v2_dimension_details,
                "unknown_dimensions": result.unknown_dimensions,
                "score_coverage": result.score_coverage,
            },
            "evidence_quality": result.evidence_quality,
            "comparability": result.comparability,
            "gate_status": result.gate_status,
            "is_provisional": result.is_provisional,
            "repeat_stats": result.repeat_stats,
            # ── NEW: execution-time breakdown and per-step resource attribution ──
            "time_breakdown": result.time_breakdown,
            "step_resource_profiles": result.step_resource_profiles,
            # ─────────────────────────────────────────────────────────────────────
            "recommendations": result.recommendations,
            "evaluation_settings": {
                "scoring_version": self.evaluation_settings.get("scoring_version", "v2"),
                "runs_per_task": self.runs_per_task,
                "main_leaderboard_core_suite_only": bool(
                    self.evaluation_settings.get("main_leaderboard_core_suite_only", True)
                ),
                "evaluation_agent_id": self.evaluation_settings.get(
                    "evaluation_agent_id",
                    self._agent_label(),
                ),
                "capability_profile_applied": bool(
                    self.evaluation_settings.get("capability_profile_applied", False)
                ),
                "capability_profile_path": self.evaluation_settings.get("capability_profile_path"),
                "declared_capabilities": self.evaluation_settings.get("declared_capabilities", {}),
                "probed_capabilities": self.evaluation_settings.get("probed_capabilities", {}),
                "trace_parser_profile": self.evaluation_settings.get("trace_parser_profile", {}),
                "resolved_capabilities": self.resolved_capabilities,
            },
            "timestamp": timestamp
        }
        
        with open(filepath, 'w') as f:
            json.dump(result_dict, f, indent=2)
        
        print(f"   📁 Result saved: {filename}")

    async def _generate_report(self, results: List[AgentEvaluationResult]):
        """Generate comprehensive agent evaluation report."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.results_dir / f"{self._artifact_prefix()}_clear_report_{timestamp}.md"
        
        # Calculate statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed_all_thresholds)
        avg_clear_score = sum(r.overall_clear_score for r in results) / total_tests
        avg_main_v2_score = sum(r.overall_v2_score for r in results) / total_tests
        avg_diag_v2_score = sum(r.overall_v2_diagnostic_score for r in results) / total_tests
        avg_score_coverage = sum(r.score_coverage for r in results) / total_tests
        avg_cost = sum(r.clear_metrics.estimated_cost_usd for r in results) / total_tests
        avg_time = sum(r.clear_metrics.total_task_time for r in results) / total_tests
        avg_steps = sum(r.clear_metrics.steps_to_completion for r in results) / total_tests
        avg_accuracy = sum(r.clear_metrics.task_completion_accuracy for r in results) / total_tests
        core_comparable_tests = sum(
            1 for r in results
            if r.comparability.get("core_status", r.comparability.get("status")) == "COMPARABLE"
        )
        full_comparable_tests = sum(
            1 for r in results
            if r.comparability.get("full_status", r.comparability.get("status")) == "COMPARABLE"
        )
        provisional_tests = sum(1 for r in results if r.is_provisional)
        main_eligible_tests = sum(
            1 for r in results if r.comparability.get("eligible_for_main_leaderboard")
        )
        full_eligible_tests = sum(
            1 for r in results if r.comparability.get("eligible_for_full_leaderboard")
        )
        avg_runs_per_task = sum(r.repeat_stats.get("run_count", 1) for r in results) / total_tests

        # Aggregate time breakdown across all results
        avg_llm_s   = sum(r.time_breakdown.get("llm_inference_s", 0)   for r in results) / total_tests
        avg_tool_s  = sum(r.time_breakdown.get("tool_execution_s", 0)  for r in results) / total_tests
        avg_coord_s = sum(r.time_breakdown.get("coordination_s", 0)    for r in results) / total_tests
        avg_llm_pct   = round(100 * avg_llm_s   / avg_time, 1) if avg_time else 0
        avg_tool_pct  = round(100 * avg_tool_s  / avg_time, 1) if avg_time else 0
        avg_coord_pct = round(100 * avg_coord_s / avg_time, 1) if avg_time else 0
        
        # Generate comprehensive report
        report = f"""# Agent CLEAR Framework Evaluation Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

This report presents comprehensive evaluation results for the `{self._agent_label()}` runtime using the Multi-Dimensional CLEAR Framework.

### 🎯 Overall Performance

| Metric | Value | Assessment |
|--------|-------|------------|
| **Success Rate** | {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%) | Overall task completion |
| **Average CLEAR Score** | {avg_clear_score:.3f}/1.000 | Main comparable score alias |
| **Average V2 Main Score** | {avg_main_v2_score:.3f}/1.000 | Comparable dimensions only |
| **Average V2 Diagnostic Score** | {avg_diag_v2_score:.3f}/1.000 | Diagnostic dimensions only |
| **Average Score Coverage** | {avg_score_coverage:.3f} | Main-dimension observability coverage |
| **Average Cost per Task** | ${avg_cost:.3f} USD | Economic efficiency |
| **Average Task Time** | {avg_time:.1f} seconds | Execution speed |
| **Average Steps** | {avg_steps:.1f} steps | Task efficiency |
| **Average Accuracy** | {avg_accuracy:.3f}/1.000 | Output quality |
| **Core Comparable Tasks** | {core_comparable_tests}/{total_tests} | Outcome-focused strict comparability |
| **Full Comparable Tasks** | {full_comparable_tests}/{total_tests} | Process + trace strict comparability |
| **Main Leaderboard Eligible** | {main_eligible_tests}/{total_tests} | Core comparable + non-provisional |
| **Full Leaderboard Eligible** | {full_eligible_tests}/{total_tests} | Full comparable + non-provisional |
| **Provisional Tasks** | {provisional_tests}/{total_tests} | Evidence coverage below threshold |
| **Average Runs per Task** | {avg_runs_per_task:.1f} | Multi-run robustness protocol |

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

| Test Case | Category | Main V2 | Diag V2 | Coverage | Cost | Time | Steps | Core Cmp | Full Cmp | Provisional | Status |
|-----------|----------|---------|---------|----------|------|------|-------|----------|----------|-------------|--------|
"""
        
        for result in results:
            status = "✅ PASS" if result.passed_all_thresholds else "❌ FAIL"
            core_cmp = result.comparability.get("core_status", result.comparability.get("status", "UNKNOWN"))
            full_cmp = result.comparability.get("full_status", result.comparability.get("status", "UNKNOWN"))
            provisional = "yes" if result.is_provisional else "no"
            report += (
                f"| {result.test_case.name} | {result.test_case.category} "
                f"| {result.overall_v2_score:.3f} | {result.overall_v2_diagnostic_score:.3f} "
                f"| {result.score_coverage:.2f} "
                f"| ${result.clear_metrics.estimated_cost_usd:.3f} | {result.clear_metrics.total_task_time:.1f}s "
                f"| {result.clear_metrics.steps_to_completion} | {core_cmp} | {full_cmp} | {provisional} | {status} |\n"
            )

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

*Report generated by Agent CLEAR Framework Evaluation System*
*Evaluation Path: {self.runtime_path}*
"""
        
        with open(report_path, 'w') as f:
            f.write(report)

        core_leaderboard_path = self.results_dir / f"{self._artifact_prefix()}_leaderboard_core_{timestamp}.csv"
        full_leaderboard_path = self.results_dir / f"{self._artifact_prefix()}_leaderboard_full_{timestamp}.csv"
        with open(core_leaderboard_path, "w", newline="", encoding="utf-8") as core_file:
            writer = csv.writer(core_file)
            writer.writerow(["test_case", "main_v2_score", "core_status", "eligible_for_main_leaderboard", "is_provisional"])
            for result in results:
                writer.writerow(
                    [
                        result.test_case.name,
                        f"{result.overall_v2_score:.6f}",
                        result.comparability.get("core_status", result.comparability.get("status", "UNKNOWN")),
                        bool(result.comparability.get("eligible_for_main_leaderboard", False)),
                        bool(result.is_provisional),
                    ]
                )
        with open(full_leaderboard_path, "w", newline="", encoding="utf-8") as full_file:
            writer = csv.writer(full_file)
            writer.writerow(["test_case", "diagnostic_v2_score", "full_status", "eligible_for_full_leaderboard", "is_provisional"])
            for result in results:
                writer.writerow(
                    [
                        result.test_case.name,
                        f"{result.overall_v2_diagnostic_score:.6f}",
                        result.comparability.get("full_status", result.comparability.get("status", "UNKNOWN")),
                        bool(result.comparability.get("eligible_for_full_leaderboard", False)),
                        bool(result.is_provisional),
                    ]
                )
        
        print(f"\n📊 Agent evaluation complete!")
        print(f"📄 Report: {report_path}")
        print(f"📁 Results: {self.results_dir}")
        print(f"📊 Core Leaderboard: {core_leaderboard_path}")
        print(f"📊 Full Leaderboard: {full_leaderboard_path}")
        
        # Console summary
        print("\n" + "=" * 80)
        print("AGENT CLEAR EVALUATION SUMMARY")
        print("=" * 80)
        print(f"Success Rate: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"CLEAR Score: {avg_clear_score:.3f}/1.000")
        print(f"Core Comparable: {core_comparable_tests}/{total_tests} | Full Comparable: {full_comparable_tests}/{total_tests}")
        print(f"Avg Cost: ${avg_cost:.3f} | Avg Time: {avg_time:.1f}s | Avg Steps: {avg_steps:.1f}")
        print("=" * 80)

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run phase3 CLEAR evaluation.")
    parser.add_argument(
        "--agent",
        default="mini-agent",
        help="Runtime adapter key/alias.",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Directory where phase3 outputs are written.",
    )
    parser.add_argument(
        "--agent-config",
        default=None,
        help="Optional path to agent config YAML (defaults to config/config.yaml).",
    )
    parser.add_argument(
        "--adapter-option",
        action="append",
        default=None,
        help="Repeatable adapter override in KEY=VALUE form (parsed as YAML scalars/lists).",
    )
    parser.add_argument(
        "--continue-agent-name",
        default=None,
        help="Continue agent name for `cn --agent <name>`.",
    )
    parser.add_argument(
        "--continue-config",
        default=None,
        help="Continue config path or hub slug for `cn --config`.",
    )
    parser.add_argument(
        "--continue-model",
        action="append",
        default=None,
        help="Repeatable Continue model slug for `cn --model`.",
    )
    parser.add_argument(
        "--continue-allow",
        action="append",
        default=None,
        help="Repeatable Continue allow policy, e.g. --continue-allow edit.",
    )
    parser.add_argument(
        "--continue-extra-arg",
        action="append",
        default=None,
        help="Repeatable raw arg appended to Continue CLI command.",
    )
    parser.add_argument(
        "--probe-agent",
        action="store_true",
        help="Run capability probe for the selected --agent before evaluation.",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Run capability probe and exit without running evaluation tasks.",
    )
    parser.add_argument(
        "--refresh-capability-profile",
        action="store_true",
        help="Force refreshing capability profile even if one already exists.",
    )
    return parser


# Example usage
async def main(argv: Optional[List[str]] = None):
    """Main execution function"""
    args = _build_arg_parser().parse_args(argv)
    base_evaluation_settings, evaluation_source = resolve_evaluation_settings(
        config_path=getattr(args, "agent_config", None),
        script_name="phase3",
        agent=getattr(args, "agent", None),
        use_capability_profile=False,
    )
    results_dir, adapter_kwargs, config_source = resolve_script_runtime_options(
        args=args,
        script_name="phase3",
        default_results_dir="artifacts/mini-agent/phase3",
    )
    adapter = create_agent_adapter(
        agent=args.agent,
        **adapter_kwargs,
    )

    probe_cfg = base_evaluation_settings.get("v2", {}).get("capability_probe", {})
    if not isinstance(probe_cfg, dict):
        probe_cfg = {}
    probe_enabled_by_config = bool(probe_cfg.get("enabled", False))
    probe_auto_refresh = bool(probe_cfg.get("auto_refresh", False))
    evaluation_settings = base_evaluation_settings
    profile_path = Path(
        base_evaluation_settings.get(
            "capability_profile_path",
            str(Path("artifacts/capability_profiles") / f"{adapter.agent_id}.json"),
        )
    )
    profile_exists = profile_path.exists()
    should_probe = bool(args.probe_agent or args.probe_only or args.refresh_capability_profile) or (
        probe_enabled_by_config
        and (probe_auto_refresh or (not profile_exists))
    )
    if should_probe:
        profile = run_capability_probe(
            adapter=adapter,
            agent_id=base_evaluation_settings.get("evaluation_agent_id", adapter.agent_id),
            declared_capabilities=base_evaluation_settings.get("declared_capabilities", {}),
            profile_dir=str(profile_path.parent),
        )
        print(f"🔎 Capability probe complete: {profile_path}")
        print(f"   Resolved capabilities: {profile.get('resolved_capabilities', {})}")
    use_capability_profile = bool(
        args.probe_agent
        or args.probe_only
        or args.refresh_capability_profile
        or probe_enabled_by_config
    )
    if use_capability_profile:
        evaluation_settings, evaluation_source = resolve_evaluation_settings(
            config_path=getattr(args, "agent_config", None),
            script_name="phase3",
            agent=getattr(args, "agent", None),
            use_capability_profile=True,
        )
    if args.probe_only:
        print("🧪 Probe-only mode complete. No evaluation run executed.")
        return

    print("🚀 Starting CLEAR Framework Evaluation")
    print("🎯 Focus: agent capabilities with pluggable runtime integration")
    print(f"Using adapter: {adapter.agent_id}")
    if config_source:
        print(f"Using config: {config_source}")
    if evaluation_source:
        print(f"Using evaluation config: {evaluation_source}")
    
    evaluator = AgentCLEAREvaluator(
        results_dir=results_dir,
        agent_adapter=adapter,
        evaluation_settings=evaluation_settings,
    )
    results = await evaluator.run_comprehensive_evaluation()
    
    print(f"\n✅ Evaluation Complete! Tested {len(results)} scenarios")
    print("📈 Agent system assessed across all CLEAR dimensions")

if __name__ == "__main__":
    asyncio.run(main())
