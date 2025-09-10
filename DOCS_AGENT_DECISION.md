# Agent Framework Decision

## Context
We need a single-agent, tool-using workflow to generate TSRs with deterministic steps and the option to fall back to the legacy path.

## Options

- AutoGen
  - Pros: Multi-agent, role-play patterns
  - Cons: Overkill for single-agent; Microsoft-centric
  - Best: Multi-agent conversational apps

- LangChain
  - Pros: Mature, many integrations, tools/agents patterns
  - Cons: Heavy; evolving API
  - Best: RAG, tool use, LLM ops

- LangGraph
  - Pros: State machines, graph workflows, deterministic control
  - Cons: Newer; smaller community
  - Best: Complex branching workflows

## Decision
Choose LangChain now with a thin agent wrapper:

- Meets current needs (single agent + tools)
- Minimal changes: we can wrap existing extractors as tools
- Easy to swap to LangGraph later for complex control

## Rationale by criteria
1) Complexity: Moderate; 5–7 steps; LangChain sufficient
2) Tool integration: Existing Python functions; easy via StructuredTool
3) State management: Short-lived per document; ConversationBufferMemory is enough
4) Team expertise: Likely familiarity with LangChain/OpenAI stack already present
5) Scalability: Parallel pipeline remains; agent runs per-TSR
6) Maintenance: Tools are modular; legacy path remains intact

## Rollout
- Feature flag `use_agent` across UI and services
- Fallback to legacy if agent fails
- Observability via logs; later add metrics

## Future
- If branching grows, consider LangGraph for explicit state diagrams and guards


