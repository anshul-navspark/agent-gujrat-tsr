from typing import Dict, Any
from agent_system.core.agents.tsr_agent import generate_tsr_with_agent


def generate_tsr_agentic(pdf_path: str, output_path: str) -> Dict[str, Any]:
    """Wrapper to invoke agentic TSR generation."""
    return generate_tsr_with_agent(pdf_path, output_path)


