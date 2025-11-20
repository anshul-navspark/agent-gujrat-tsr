"""
TSR Generation Agent - Intelligent agent for Title Search Report generation
"""
from typing import Dict, List, Any, Optional
import json
import logging
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate
from langchain.tools import StructuredTool
import os
from dotenv import load_dotenv

from agent_system.core.tools.tsr_agent_tools import AVAILABLE_TOOLS


class TSRAgent:
    """Intelligent agent for TSR generation with tool calling capabilities"""
    
    def __init__(self, llm: Optional[ChatGoogleGenerativeAI] = None, verbose: bool = True):
        self.logger = logging.getLogger(__name__)
        load_dotenv()
        
        self.llm = llm or self._create_default_llm()
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        self.tools = self._create_tools()
        self.agent = self._create_agent()
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=verbose,
            max_iterations=10,
            early_stopping_method="generate"
        )
        
    def _create_default_llm(self) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.5-flash'),
            google_api_key=os.getenv('GEMINI_API_KEY', ''),
            temperature=0.1,
            convert_system_message_to_human=True,
        )
    
    def _create_tools(self) -> List[StructuredTool]:
        tools: List[StructuredTool] = []
        
        def extract_land_details(text: str, section_hint: str = "") -> str:
            tool = AVAILABLE_TOOLS["extract_land_details"]
            result = tool.run(text, section_hint)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=extract_land_details,
            name="extract_land_details",
            description="Extract land details (village, taluka, survey number, etc.) from document text"
        ))
        
        def extract_entry_details(text: str, entry_numbers: str = "") -> str:
            tool = AVAILABLE_TOOLS["extract_entry_details"]
            entry_list = [e.strip() for e in entry_numbers.split(",") if e.strip()] if entry_numbers else None
            result = tool.run(text, entry_list)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=extract_entry_details,
            name="extract_entry_details",
            description="Extract mutation entry details; optionally provide comma-separated entry numbers"
        ))
        
        def identify_sections(text: str) -> str:
            tool = AVAILABLE_TOOLS["identify_sections"]
            result = tool.run(text)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=identify_sections,
            name="identify_sections",
            description="Identify and map sections (Land Details, Entry Details, etc.) in the document"
        ))
        
        def validate_extraction(land_details_json: str, entries_json: str) -> str:
            tool = AVAILABLE_TOOLS["validate_extraction"]
            land_details = json.loads(land_details_json or '{}')
            entries = json.loads(entries_json or '[]')
            result = tool.run(land_details, entries)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=validate_extraction,
            name="validate_extraction",
            description="Validate extracted land details and entries for completeness and consistency"
        ))
        
        def generate_findings(land_details_json: str, entries_json: str, jurisdiction: str = "") -> str:
            tool = AVAILABLE_TOOLS["generate_findings"]
            land_details = json.loads(land_details_json or '{}')
            entries = json.loads(entries_json or '[]')
            result = tool.run(land_details, entries, jurisdiction)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=generate_findings,
            name="generate_findings",
            description="Generate standard TSR findings based on extracted data"
        ))
        
        def generate_tsr_document(land_details_json: str, entries_json: str, findings_json: str, output_path: str) -> str:
            tool = AVAILABLE_TOOLS["generate_tsr_document"]
            land_details = json.loads(land_details_json or '{}')
            entries = json.loads(entries_json or '[]')
            findings = json.loads(findings_json or '[]')
            result = tool.run(land_details, entries, findings, output_path)
            return json.dumps(result, ensure_ascii=False)
        tools.append(StructuredTool.from_function(
            func=generate_tsr_document,
            name="generate_tsr_document",
            description="Generate the final TSR document in DOCX format"
        ))
        
        return tools
    
    def _create_agent(self):
        system_prompt = """You are an expert TSR (Title Search Report) generation agent. Analyze land record documents and generate comprehensive TSR reports.

You have access to the following tools:
{tools}

Workflow:
1) identify_sections → 2) extract_land_details → 3) extract_entry_details → 4) validate_extraction → 5) retry missing pieces → 6) generate_findings → 7) generate_tsr_document

Principles:
- Be thorough; capture all entry numbers and details
- Validate consistency; correct obvious inconsistencies
- Prefer faithful extraction over guesswork; include notes if uncertain
- Handle Gujarati and English

Use this I/O format:
Thought: ...
Action: one of {tool_names}
Action Input: ...
Observation: ...
... repeat ...
Final Answer: short summary of what was generated

{chat_history}
Human: {input}
{agent_scratchpad}
"""
        prompt = ChatPromptTemplate.from_template(system_prompt)
        agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        return agent
    
    def generate_tsr(self, pdf_text: str, output_path: str) -> Dict[str, Any]:
        self.logger.info("Starting TSR generation with agent")
        try:
            request = (
                "Generate a Title Search Report (TSR) from this land record. Save to: "
                + output_path
                + "\n---\n"
                + (pdf_text[:5000] if pdf_text else "")
                + ("\n[... document continues ...]" if pdf_text and len(pdf_text) > 5000 else "")
                + "\n---\n"
            )
            result = self.executor.run(request)
            return {
                "success": True,
                "output_path": output_path,
                "agent_response": result,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            self.logger.error(f"Agent failed to generate TSR: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def reset_memory(self):
        self.memory.clear()


def generate_tsr_with_agent(pdf_path: str, output_path: str) -> Dict[str, Any]:
    """Convenience function to generate TSR via agent from a PDF path."""
    from tsr_generator.utils.pdf_utils import extract_text_from_pdf
    pdf_text = extract_text_from_pdf(pdf_path)
    if not pdf_text:
        return {"success": False, "error": "Failed to extract text from PDF"}
    agent = TSRAgent(verbose=True)
    try:
        result = agent.generate_tsr(pdf_text, output_path)
        return result
    finally:
        agent.reset_memory()


