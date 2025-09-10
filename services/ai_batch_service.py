"""
Optimized AI batch processing service for TSR generation.

This service batches AI calls and pre-computes prompts for better performance.
"""

import asyncio
import json
import time
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import queue
import threading

from tsr_generator.utils.pdf_utils import extract_text_from_pdf
from tsr_generator.extractors.land_details import extract_land_records_ai
from tsr_generator.extractors.entry_details import extract_entry_details_ai, identify_all_entry_numbers
from tsr_generator.extractors.findings import generate_findings_table
from tsr_generator.document.tsr_document import create_tsr_document


@dataclass
class AITask:
    """Represents an AI processing task"""
    task_id: str
    pdf_path: str
    pdf_text: Optional[str] = None
    land_details: Optional[Dict] = None
    entry_details: Optional[List] = None
    findings: Optional[List] = None
    status: str = "pending"  # pending, processing, completed, failed
    error: Optional[str] = None


class AIBatchService:
    """Optimized AI service for batch processing TSR generation"""
    
    def __init__(
        self,
        max_concurrent_ai_calls: int = 3,
        batch_size: int = 5,
        logger: Optional[logging.Logger] = None
    ):
        self.max_concurrent_ai_calls = max_concurrent_ai_calls
        self.batch_size = batch_size
        self.logger = logger or logging.getLogger(__name__)
        
        # Task tracking
        self.tasks: Dict[str, AITask] = {}
        
        # Processing queues
        self.pdf_text_queue = queue.Queue()
        self.ai_processing_queue = queue.Queue()
        
        # Executor for AI calls
        self.ai_executor = ThreadPoolExecutor(max_workers=max_concurrent_ai_calls)
        
        # Pre-computed prompt templates (to avoid re-creating them each time)
        self._land_details_prompt_template = self._prepare_land_details_prompt()
        self._entry_details_prompt_template = self._prepare_entry_details_prompt()
        self._findings_prompt_template = self._prepare_findings_prompt()
    
    def _prepare_land_details_prompt(self) -> str:
        """Pre-compute the land details extraction prompt template"""
        return """
        Extract land record details from the following Gujarati land record text and return as JSON.
        
        Required fields:
        - village_name: Name of the village
        - taluka_name: Name of the taluka
        - district_name: Name of the district
        - survey_number: Survey/Block number
        - total_area: Total area of the land
        - nature_of_land: Classification/nature of land
        - owner: Current owner(s) name(s)
        - old_survey_number: Old survey number if available
        
        Text: {pdf_text}
        
        Return only valid JSON:
        """
    
    def _prepare_entry_details_prompt(self) -> str:
        """Pre-compute the entry details extraction prompt template"""
        return """
        Extract mutation entry details from the following Gujarati land record text.
        Focus on the "Entry Details" section and return as JSON array.
        
        For each entry, extract:
        - entry_number: Entry/mutation number
        - date: Date of the entry
        - type: Type of mutation (Sale, Mortgage, Release, etc.)
        - description: Brief description
        - parties_involved: Names of people involved
        
        Text: {pdf_text}
        
        Return only valid JSON array:
        """
    
    def _prepare_findings_prompt(self) -> str:
        """Pre-compute the findings prompt template"""
        return """
        Generate standard TSR findings based on the land record analysis.
        Return as JSON array of finding objects with 'text' field.
        
        Text: {pdf_text}
        
        Return only valid JSON array:
        """
    
    def submit_task(self, task_id: str, pdf_path: str) -> str:
        """Submit a PDF for AI processing"""
        task = AITask(task_id=task_id, pdf_path=pdf_path)
        self.tasks[task_id] = task
        
        # Add to processing queue
        self.pdf_text_queue.put(task)
        self.logger.info(f"AI task submitted: {task_id}")
        
        return task_id
    
    def _extract_pdf_text_batch(self, tasks: List[AITask]):
        """Extract text from multiple PDFs in parallel"""
        def extract_single_text(task: AITask):
            try:
                task.pdf_text = extract_text_from_pdf(task.pdf_path)
                if task.pdf_text:
                    task.status = "text_extracted"
                else:
                    task.status = "failed"
                    task.error = "Failed to extract PDF text"
            except Exception as e:
                task.status = "failed"
                task.error = f"PDF text extraction error: {str(e)}"
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=min(len(tasks), 4)) as executor:
            futures = [executor.submit(extract_single_text, task) for task in tasks]
            for future in futures:
                future.result()  # Wait for completion
    
    def _process_ai_batch(self, tasks: List[AITask]):
        """Process AI calls for a batch of tasks"""
        # Filter tasks that have PDF text
        valid_tasks = [t for t in tasks if t.pdf_text and t.status == "text_extracted"]
        
        if not valid_tasks:
            return
        
        # Batch process AI calls
        def process_land_details(tasks_batch):
            for task in tasks_batch:
                try:
                    task.land_details = extract_land_records_ai(task.pdf_text)
                    self.logger.info(f"Land details extracted for {task.task_id}")
                except Exception as e:
                    self.logger.error(f"Land details extraction failed for {task.task_id}: {e}")
                    task.error = f"Land details extraction error: {str(e)}"
        
        def process_entry_details(tasks_batch):
            for task in tasks_batch:
                try:
                    task.entry_details = extract_entry_details_ai(task.pdf_text)
                    self.logger.info(f"Entry details extracted for {task.task_id}")
                except Exception as e:
                    self.logger.error(f"Entry details extraction failed for {task.task_id}: {e}")
                    task.error = f"Entry details extraction error: {str(e)}"
        
        def process_findings(tasks_batch):
            for task in tasks_batch:
                try:
                    task.findings = generate_findings_table(task.pdf_text)
                    self.logger.info(f"Findings generated for {task.task_id}")
                except Exception as e:
                    self.logger.error(f"Findings generation failed for {task.task_id}: {e}")
                    task.error = f"Findings generation error: {str(e)}"
        
        # Run AI extractions in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            land_future = executor.submit(process_land_details, valid_tasks)
            entry_future = executor.submit(process_entry_details, valid_tasks)
            findings_future = executor.submit(process_findings, valid_tasks)
            
            # Wait for all AI processing to complete
            land_future.result()
            entry_future.result()
            findings_future.result()
        
        # Update task status
        for task in valid_tasks:
            if task.land_details and task.entry_details and task.findings:
                task.status = "ai_completed"
            elif not task.error:
                task.status = "failed"
                task.error = "Some AI extractions failed"
    
    def _generate_documents_batch(self, tasks: List[AITask]):
        """Generate DOCX documents for completed AI tasks"""
        completed_tasks = [t for t in tasks if t.status == "ai_completed"]
        
        def generate_single_document(task: AITask):
            try:
                # Generate output path
                tsr_path = task.pdf_path.replace('.pdf', '.docx').replace('/pdfs/', '/tsr/')
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(tsr_path), exist_ok=True)
                
                # Create TSR document
                create_tsr_document(
                    task.entry_details,
                    task.land_details,
                    task.findings,
                    tsr_path
                )
                
                task.status = "completed"
                self.logger.info(f"TSR document generated for {task.task_id}: {tsr_path}")
                
            except Exception as e:
                task.status = "failed"
                task.error = f"Document generation error: {str(e)}"
                self.logger.error(f"Document generation failed for {task.task_id}: {e}")
        
        # Generate documents in parallel
        with ThreadPoolExecutor(max_workers=min(len(completed_tasks), 4)) as executor:
            futures = [executor.submit(generate_single_document, task) for task in completed_tasks]
            for future in futures:
                future.result()
    
    def process_batch(self, max_tasks: Optional[int] = None) -> int:
        """Process a batch of pending tasks"""
        # Collect pending tasks
        pending_tasks = [
            task for task in self.tasks.values() 
            if task.status == "pending"
        ]
        
        if not pending_tasks:
            return 0
        
        # Limit batch size
        if max_tasks:
            pending_tasks = pending_tasks[:max_tasks]
        else:
            pending_tasks = pending_tasks[:self.batch_size]
        
        self.logger.info(f"Processing AI batch of {len(pending_tasks)} tasks")
        
        # Stage 1: Extract PDF text in parallel
        self._extract_pdf_text_batch(pending_tasks)
        
        # Stage 2: Process AI calls in parallel
        self._process_ai_batch(pending_tasks)
        
        # Stage 3: Generate documents in parallel
        self._generate_documents_batch(pending_tasks)
        
        completed_count = len([t for t in pending_tasks if t.status == "completed"])
        self.logger.info(f"AI batch completed: {completed_count}/{len(pending_tasks)} successful")
        
        return completed_count
    
    def get_task_status(self, task_id: str) -> Optional[AITask]:
        """Get the status of a specific task"""
        return self.tasks.get(task_id)
    
    def get_completed_tasks(self) -> List[AITask]:
        """Get all completed tasks"""
        return [task for task in self.tasks.values() if task.status == "completed"]
    
    def get_failed_tasks(self) -> List[AITask]:
        """Get all failed tasks"""
        return [task for task in self.tasks.values() if task.status == "failed"]
    
    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics"""
        stats = {}
        for status in ["pending", "text_extracted", "ai_completed", "completed", "failed"]:
            stats[status] = len([t for t in self.tasks.values() if t.status == status])
        return stats
    
    def clear_completed_tasks(self):
        """Clear completed tasks to free memory"""
        completed_ids = [
            task_id for task_id, task in self.tasks.items() 
            if task.status in ["completed", "failed"]
        ]
        for task_id in completed_ids:
            del self.tasks[task_id]
        
        self.logger.info(f"Cleared {len(completed_ids)} completed tasks")


# Optimized TSR generation function that uses the batch service
def generate_tsr_optimized(pdf_path: str, output_path: str, batch_service: Optional[AIBatchService] = None) -> bool:
    """
    Optimized TSR generation that can work with batch processing
    """
    import os
    
    try:
        if batch_service:
            # Use batch service
            task_id = os.path.basename(pdf_path)
            batch_service.submit_task(task_id, pdf_path)
            batch_service.process_batch(max_tasks=1)
            
            task = batch_service.get_task_status(task_id)
            if task and task.status == "completed":
                # Move the generated file to the desired output path
                generated_path = pdf_path.replace('.pdf', '.docx').replace('/pdfs/', '/tsr/')
                if os.path.exists(generated_path) and generated_path != output_path:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    os.rename(generated_path, output_path)
                return True
            else:
                return False
        else:
            # Fallback to original method
            from tsr_generator import generate_tsr_from_pdf
            result = generate_tsr_from_pdf(pdf_path, output_path)
            return result.get('success', False) if isinstance(result, dict) else True
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Optimized TSR generation failed: {e}")
        return False
