```mermaid
graph TD
      A[Start: Agent System] --> B[Phase 1: CLEAR Framework Assessment]

      B --> B1[Cost Analysis]
      B --> B2[Latency Analysis]
      B --> B3[Efficiency Analysis]
      B --> B4[Assurance Analysis]
      B --> B5[Reliability Analysis]

      B1 --> C{Poor Reasoning Quality Detected?}
      B2 --> C
      B3 --> C
      B4 --> C
      B5 --> C

      C -->|Yes| D[🔥 REASONING BOTTLENECK IDENTIFIED]
      C -->|No| E[Phase 2: Academic Benchmark Assessment]

      E --> E1[MMLU-style Correctness]
      E --> E2[HumanEval Execution]
      E --> E3[Chain-of-Thought Quality]
      E --> E4[SWE-Agent Completeness]

      E1 --> F{Academic Scores < Threshold?}
      E2 --> F
      E3 --> F
      E4 --> F

      F -->|Yes| G[⚠️ KNOWLEDGE/CAPABILITY BOTTLENECK]
      F -->|No| H[Phase 3: System Resource Assessment]

      H --> H1[CPU Utilization Analysis]
      H --> H2[Memory Usage Patterns]
      H --> H3[I/O Performance]
      H --> H4[Network Bottlenecks]

      H1 --> I{Resource Constraints Found?}
      H2 --> I
      H3 --> I
      H4 --> I

      I -->|Yes| J[🔧 RESOURCE BOTTLENECK]
      I -->|No| K[✅ OPTIMIZATION OPPORTUNITIES]

      D --> D1[Specific Reasoning Fixes]
      G --> G1[Specific Knowledge/Capability Fixes]
      J --> J1[Specific Resource Fixes]
      K --> K1[Specific Optimization Actions]

      D1 --> L[Implementation Roadmap]
      G1 --> L
      J1 --> L
      K1 --> L
```
  Specific Bottleneck Categories Based on Your Matrices

#  Phase 1 CLEAR Framework → Specific Issues
```mermaid
  graph LR
      A[CLEAR Metrics] --> B[Cost Issues]
      A --> C[Latency Issues]
      A --> D[Efficiency Issues]
      A --> E[Assurance Issues]
      A --> F[Reliability Issues]

      B --> B1[Excessive API Calls<br/>Fix: Optimize LLM usage]
      B --> B2[High Token Consumption<br/>Fix: Context management]
      B --> B3[Tool Overuse<br/>Fix: Tool selection logic]

      C --> C1[Slow LLM Response<br/>Fix: Model optimization]
      C --> C2[Long Tool Execution<br/>Fix: Tool performance]
      C --> C3[Too Many Steps<br/>Fix: Planning efficiency]

      D --> D1[Poor Tool Selection<br/>Fix: Selection algorithms]
      D --> D2[Resource Waste<br/>Fix: Resource management]
      D --> D3[Low Steps/Second<br/>Fix: Execution pipeline]

      E --> E1[Poor Task Accuracy<br/>Fix: Reasoning quality]
      E --> E2[Low Output Quality<br/>Fix: Response generation]
      E --> E3[Weak Reasoning<br/>Fix: Chain-of-thought]

      F --> F1[Execution Failures<br/>Fix: Error handling]
      F --> F2[Poor Error Recovery<br/>Fix: Recovery logic]
      F --> F3[System Instability<br/>Fix: Reliability measures]
```
#  Phase 2 Academic Benchmarks → Specific Issues
```mermaid
  graph LR
      A[Academic Metrics] --> B[MMLU Issues]
      A --> C[HumanEval Issues]
      A --> D[Chain-of-Thought Issues]
      A --> E[SWE-Agent Issues]

      B --> B1[Factual Accuracy Low<br/>Fix: Knowledge base updates]
      B --> B2[Keyword Matching Poor<br/>Fix: Response formatting]

      C --> C1[Code Execution Fails<br/>Fix: Syntax validation]
      C --> C2[Logic Errors<br/>Fix: Algorithm training]

      D --> D1[No Step-by-Step Reasoning<br/>Fix: Reasoning prompts]
      D --> D2[Poor Problem Decomposition<br/>Fix: Planning templates]
      D --> D3[Weak Explanation<br/>Fix: Explanation training]

      E --> E1[Incomplete Task Coverage<br/>Fix: Task decomposition]
      E --> E2[Missing Components<br/>Fix: Completeness checking]
```

#  Phase 3 System Resources → Specific Issues
```mermaid
  graph LR
      A[System Metrics] --> B[CPU Bottleneck]
      A --> C[Memory Bottleneck]
      A --> D[I/O Bottleneck]
      A --> E[Network Bottleneck]

      B --> B1[High CPU During Thinking<br/>Fix: LLM optimization]
      B --> B2[CPU Spikes in Tools<br/>Fix: Tool efficiency]
      B --> B3[Processing Queue Buildup<br/>Fix: Parallel processing]

      C --> C1[Context Window Pressure<br/>Fix: Context management]
      C --> C2[Memory Leaks<br/>Fix: Memory cleanup]
      C --> C3[Swap Usage<br/>Fix: Memory limits]

      D --> D1[Disk I/O Heavy Tools<br/>Fix: I/O optimization]
      D --> D2[File Operation Delays<br/>Fix: Async operations]
      D --> D3[Log Writing Bottleneck<br/>Fix: Logging efficiency]

      E --> E1[API Call Latency<br/>Fix: Connection pooling]
      E --> E2[Network Bandwidth<br/>Fix: Request optimization]
      E --> E3[Rate Limiting<br/>Fix: Request throttling]
```
  Your Actual Implementation Results

  Based on your Mini-Agent evaluation:

  Detected Pattern: Reasoning Quality Bottleneck
```
  Phase 1 CLEAR Results:
  ├── Cost: ✅ Good (efficient tool usage)
  ├── Latency: ✅ Acceptable (within time limits)
  ├── Efficiency: ✅ Good (tool selection accuracy: 1.0)
  ├── Assurance: ❌ Poor (reasoning quality consistently low)
  └── Reliability: ✅ Good (high success rate)

  Phase 2 Academic Results:
  ├── MMLU-style: ❌ Poor keyword matching
  ├── HumanEval: ✅ Code executes correctly
  ├── Chain-of-Thought: ❌ Poor step-by-step reasoning
  └── SWE-Agent: ❌ Poor problem decomposition
```
  Conclusion: REASONING BOTTLENECK (not resource or technical)

  Specific Implementation Roadmap

  Immediate Actions (Week 1):

  1. Enhance System Prompts:
  Before: "Create a file with Hello World"
  After: "Step 1: Analyze the request
          Step 2: Plan the file creation approach
          Step 3: Execute file creation
          Step 4: Verify success"
  2. Add Reasoning Validation:
  Check: Does response show problem breakdown?
  Check: Does response explain reasoning?
  Check: Does response validate approach?

  Short-term Actions (Week 2-3):

  1. Implement Chain-of-Thought Templates
  2. Add Reasoning Quality Scoring
  3. Create Problem Decomposition Examples

  Long-term Actions (Month 1):

  1. Reasoning Quality Monitoring Dashboard
  2. Automated Reasoning Validation
  3. Continuous Improvement Pipeline

  This shows your systematic examination framework identifies specific, actionable bottlenecks rather than vague categories - exactly what developers need for practical
  improvement!