"""
TSR Generation Agent - Intelligent agent for Title Search Report generation
"""
from typing import Dict, List, Any, Optional, Tuple
import json
import logging
from datetime import datetime
from langchain_openai import AzureChatOpenAI
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv

from tsr_agent_tools import AVAILABLE_TOOLS


class TSRAgent:
    """Intelligent agent for TSR generation with tool calling capabilities"""
    
    def __init__(self, llm: Optional[AzureChatOpenAI] = None, verbose: bool = True):
        """
        Initialize the TSR Agent
        
        Args:
            llm: Language model instance (creates default if not provided)
            verbose: Whether to show agent reasoning
        """
        self.logger = logging.getLogger(__name__)
        load_dotenv()
        
        # Initialize LLM
        self.llm = llm or self._create_default_llm()
        
        # Initialize memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Create tools
        self.tools = self._create_tools()
        
        # Create agent
        self.agent = self._create_agent()
        
        # Create executor
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=verbose,
            max_iterations=10,
            early_stopping_method="generate"
        )
        
    def _create_default_llm(self) -> AzureChatOpenAI:
        """Create default LLM instance"""
        return AzureChatOpenAI(
            model=os.getenv('AI_MODEL_NAME', 'gpt-4'),
            api_version=os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-15-preview'),
            azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', ''),
            api_key=os.getenv('AZURE_OPENAI_KEY', ''),
            temperature=0.1
        )
    
    def _create_tools(self) -> List[StructuredTool]:
        """Create tools for the agent"""
        tools = []
        
        # Extract Land Details Tool
        def extract_land_details(text: str, section_hint: str = "") -> str:
            """Extract land details from document text"""
            tool = AVAILABLE_TOOLS["extract_land_details"]
            result = tool.run(text, section_hint)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=extract_land_details,
            name="extract_land_details",
            description="Extract land details (village, taluka, survey number, etc.) from document text"
        ))
        
        # Extract Entry Details Tool
        def extract_entry_details(text: str, entry_numbers: str = "") -> str:
            """Extract mutation entry details from document text"""
            tool = AVAILABLE_TOOLS["extract_entry_details"]
            entry_list = entry_numbers.split(",") if entry_numbers else None
            result = tool.run(text, entry_list)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=extract_entry_details,
            name="extract_entry_details",
            description="Extract mutation entry details from document text. Optionally provide comma-separated entry numbers to look for specific entries."
        ))
        
        # Identify Sections Tool
        def identify_sections(text: str) -> str:
            """Identify different sections in the document"""
            tool = AVAILABLE_TOOLS["identify_sections"]
            result = tool.run(text)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=identify_sections,
            name="identify_sections",
            description="Identify and map different sections (Land Details, Entry Details, etc.) in the document"
        ))
        
        # Validate Extraction Tool
        def validate_extraction(land_details_json: str, entries_json: str) -> str:
            """Validate extracted data for completeness and consistency"""
            tool = AVAILABLE_TOOLS["validate_extraction"]
            land_details = json.loads(land_details_json)
            entries = json.loads(entries_json)
            result = tool.run(land_details, entries)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=validate_extraction,
            name="validate_extraction",
            description="Validate extracted land details and entries for completeness and consistency. Provide JSON strings for both parameters."
        ))
        
        # Generate Findings Tool
        def generate_findings(land_details_json: str, entries_json: str, jurisdiction: str = "") -> str:
            """Generate standard TSR findings"""
            tool = AVAILABLE_TOOLS["generate_findings"]
            land_details = json.loads(land_details_json)
            entries = json.loads(entries_json)
            result = tool.run(land_details, entries, jurisdiction)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=generate_findings,
            name="generate_findings",
            description="Generate standard TSR findings based on extracted data. Provide JSON strings for land_details and entries."
        ))
        
        # Generate TSR Document Tool
        def generate_tsr_document(land_details_json: str, entries_json: str, 
                                findings_json: str, output_path: str) -> str:
            """Generate final TSR document"""
            tool = AVAILABLE_TOOLS["generate_tsr_document"]
            land_details = json.loads(land_details_json)
            entries = json.loads(entries_json)
            findings = json.loads(findings_json)
            result = tool.run(land_details, entries, findings, output_path)
            return json.dumps(result, indent=2)
        
        tools.append(StructuredTool.from_function(
            func=generate_tsr_document,
            name="generate_tsr_document",
            description="Generate the final TSR document in DOCX format. Provide JSON strings for all data parameters."
        ))
        
        return tools
    
    def _create_agent(self):
        """Create the agent with appropriate prompt"""
        system_prompt = """You are an expert TSR (Title Search Report) generation agent. Your task is to analyze land record documents and generate comprehensive TSR reports.

You have access to the following tools:
{tools}

Your workflow should be:
1. First, identify the sections in the document using identify_sections
2. Extract land details from the appropriate section using extract_land_details
3. Extract all mutation entry details using extract_entry_details
4. Validate the extracted data using validate_extraction
5. If validation fails, re-extract missing information with better context
6. Generate findings using generate_findings
7. Create the final TSR document using generate_tsr_document

Key principles:
- Be thorough and extract ALL information from the document
- Validate data consistency and completeness
- If information is unclear, make intelligent assumptions but note them
- Ensure all entry numbers mentioned in the document are captured
- Format descriptions properly according to TSR standards
- Handle both English and Gujarati text appropriately

Use the following format:
Thought: Analysis of what needs to be done
Action: the action to take (one of {tool_names})
Action Input: the input to the action
Observation: the result of the action
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I have completed all necessary extractions and validations
Final Answer: Summary of the TSR generation process and results

Begin!

{chat_history}
Human: {input}
{agent_scratchpad}"""
        
        prompt = ChatPromptTemplate.from_template(system_prompt)
        
        agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        return agent
    
    def generate_tsr(self, pdf_text: str, output_path: str) -> Dict[str, Any]:
        """
        Generate a TSR from PDF text using the agent
        
        Args:
            pdf_text: Extracted text from the PDF document
            output_path: Path where the TSR document should be saved
            
        Returns:
            Dictionary with generation results
        """
        self.logger.info("Starting TSR generation with agent")
        
        try:
            # Prepare the request
            request = f"""
            I need you to generate a Title Search Report (TSR) from the following land record document.
            The final TSR should be saved to: {output_path}
            
            Here is the document text:
            ---
            {pdf_text[:5000]}  # Provide substantial portion of text
            {"[... document continues ...]" if len(pdf_text) > 5000 else ""}
            ---
            
            Please analyze this document thoroughly and generate a complete TSR report.
            """
            
            # Run the agent
            result = self.executor.run(request)
            
            # Parse the result
            return {
                "success": True,
                "output_path": output_path,
                "agent_response": result,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Agent failed to generate TSR: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def reset_memory(self):
        """Reset the agent's conversation memory"""
        self.memory.clear()


# Example usage function
def generate_tsr_with_agent(pdf_path: str, output_path: str) -> Dict[str, Any]:
    """
    Generate TSR using the intelligent agent
    
    Args:
        pdf_path: Path to the PDF file
        output_path: Path where TSR should be saved
        
    Returns:
        Generation results
    """
    from tsr_generator.utils.pdf_utils import extract_text_from_pdf
    
    # Extract text from PDF
    pdf_text = extract_text_from_pdf(pdf_path)
    
    if not pdf_text:
        return {
            "success": False,
            "error": "Failed to extract text from PDF"
        }
    
    # Create agent and generate TSR
    agent = TSRAgent(verbose=True)
    result = agent.generate_tsr(pdf_text, output_path)
    
    # Clean up
    agent.reset_memory()
    
    return result
