"""
High-performance parallel processing service with producer-consumer pipeline architecture.

This service separates PDF fetching from TSR generation and processes them in parallel
pipelines for significantly improved performance.
"""

import os
import time
import queue
import asyncio
import threading
import concurrent.futures
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import logging

from services.processing_service import ProcessResult, LandRecordProcessor
from tsr_generator import generate_tsr_from_pdf


@dataclass
class PipelineTask:
    """Represents a task in the processing pipeline"""
    record_id: str
    district_guj: str
    taluka_guj: str
    village_guj: str
    survey_number_guj: str
    row_idx: int
    sheet_name: str
    pdf_path: Optional[str] = None
    tsr_path: Optional[str] = None
    status: str = "queued"  # queued, pdf_fetching, pdf_ready, tsr_generating, completed, failed
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    pdf_complete_time: Optional[datetime] = None
    tsr_complete_time: Optional[datetime] = None


@dataclass
class PipelineStats:
    """Statistics for the processing pipeline"""
    total_tasks: int = 0
    pdf_queue_size: int = 0
    tsr_queue_size: int = 0
    pdf_workers_active: int = 0
    tsr_workers_active: int = 0
    completed_count: int = 0
    failed_count: int = 0
    avg_pdf_time: float = 0.0
    avg_tsr_time: float = 0.0
    overall_throughput: float = 0.0


class ParallelProcessingService:
    """High-performance parallel processing service with pipeline architecture"""
    
    def __init__(
        self,
        output_base_dir: str = "output",
        headless: bool = True,
        max_pdf_workers: int = 2,  # Limited by Selenium stability
        max_tsr_workers: int = 4,  # Can be higher since it's CPU/AI bound
        pdf_queue_size: int = 10,
        tsr_queue_size: int = 20,
        logger: Optional[logging.Logger] = None,
        use_agent: bool = False,
    ):
        self.output_base_dir = output_base_dir
        self.headless = headless
        self.max_pdf_workers = max_pdf_workers
        self.max_tsr_workers = max_tsr_workers
        self.logger = logger or logging.getLogger(__name__)
        self.use_agent = use_agent
        
        # Queues for pipeline stages
        self.pdf_queue = queue.Queue(maxsize=pdf_queue_size)
        self.tsr_queue = queue.Queue(maxsize=tsr_queue_size)
        
        # Task tracking
        self.tasks: Dict[str, PipelineTask] = {}
        self.stats = PipelineStats()
        
        # Control flags
        self.shutdown_flag = threading.Event()
        self.pause_flag = threading.Event()
        
        # Worker pools
        self.pdf_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_pdf_workers)
        self.tsr_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_tsr_workers)
        
        # Progress callbacks
        self.progress_callbacks: List[Callable[[PipelineTask, PipelineStats], None]] = []
        
        # Pre-create processor instances to avoid overhead
        self._pdf_processors = [
            LandRecordProcessor(output_base_dir=output_base_dir, headless=headless, logger=self.logger)
            for _ in range(max_pdf_workers)
        ]
        self._pdf_processor_queue = queue.Queue()
        for processor in self._pdf_processors:
            self._pdf_processor_queue.put(processor)
    
    def add_progress_callback(self, callback: Callable[[PipelineTask, PipelineStats], None]):
        """Add a callback to be notified of progress updates"""
        self.progress_callbacks.append(callback)
    
    def _notify_progress(self, task: PipelineTask):
        """Notify all progress callbacks"""
        self._update_stats()
        for callback in self.progress_callbacks:
            try:
                callback(task, self.stats)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
    
    def _update_stats(self):
        """Update pipeline statistics"""
        self.stats.total_tasks = len(self.tasks)
        self.stats.pdf_queue_size = self.pdf_queue.qsize()
        self.stats.tsr_queue_size = self.tsr_queue.qsize()
        
        completed_tasks = [t for t in self.tasks.values() if t.status == "completed"]
        failed_tasks = [t for t in self.tasks.values() if t.status == "failed"]
        
        self.stats.completed_count = len(completed_tasks)
        self.stats.failed_count = len(failed_tasks)
        
        # Calculate average times
        if completed_tasks:
            pdf_times = []
            tsr_times = []
            for task in completed_tasks:
                if task.start_time and task.pdf_complete_time:
                    pdf_times.append((task.pdf_complete_time - task.start_time).total_seconds())
                if task.pdf_complete_time and task.tsr_complete_time:
                    tsr_times.append((task.tsr_complete_time - task.pdf_complete_time).total_seconds())
            
            self.stats.avg_pdf_time = sum(pdf_times) / len(pdf_times) if pdf_times else 0
            self.stats.avg_tsr_time = sum(tsr_times) / len(tsr_times) if tsr_times else 0
    
    def _pdf_worker(self):
        """Worker function for PDF fetching"""
        self.logger.info("PDF worker started")
        processor = None
        
        try:
            processor = self._pdf_processor_queue.get(timeout=1)
        except queue.Empty:
            self.logger.warning("No PDF processor available")
            return
        
        try:
            while not self.shutdown_flag.is_set():
                try:
                    # Wait for pause to be cleared
                    while self.pause_flag.is_set() and not self.shutdown_flag.is_set():
                        time.sleep(0.1)
                    
                    if self.shutdown_flag.is_set():
                        break
                    
                    # Get task from queue
                    task = self.pdf_queue.get(timeout=1)
                    if task is None:  # Shutdown signal
                        break
                    
                    self.logger.info(f"PDF worker processing: {task.record_id}")
                    task.status = "pdf_fetching"
                    task.start_time = datetime.now()
                    self._notify_progress(task)
                    
                    # Fetch PDF
                    result = processor.fetch_pdf_and_tsr(
                        district_guj=task.district_guj,
                        taluka_guj=task.taluka_guj,
                        village_guj=task.village_guj,
                        survey_number_guj=task.survey_number_guj,
                        regenerate_pdf=False,  # Always check for existing PDFs
                        generate_tsr=False  # Only fetch PDF
                    )
                    
                    if result.success:
                        task.pdf_path = result.pdf_path
                        task.status = "pdf_ready"
                        task.pdf_complete_time = datetime.now()
                        
                        # Add to TSR queue (prefer waiting briefly over failing the task)
                        try:
                            self.tsr_queue.put(task, timeout=10)
                            self.logger.info(f"PDF ready, queued for TSR: {task.record_id}")
                        except queue.Full:
                            # As a last resort, block until space is available to avoid dropping work
                            self.logger.warning("TSR queue full; blocking enqueue to avoid losing task")
                            self.tsr_queue.put(task)
                            self.logger.info(f"PDF ready, queued for TSR after wait: {task.record_id}")
                    else:
                        task.status = "failed"
                        task.error = result.error
                        self.logger.error(f"PDF fetch failed for {task.record_id}: {result.error}")
                    
                    self._notify_progress(task)
                    self.pdf_queue.task_done()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"PDF worker error: {e}")
                    if 'task' in locals():
                        task.status = "failed"
                        task.error = str(e)
                        self._notify_progress(task)
                        self.pdf_queue.task_done()
        
        finally:
            if processor:
                self._pdf_processor_queue.put(processor)
            self.logger.info("PDF worker stopped")
    
    def _tsr_worker(self):
        """Worker function for TSR generation"""
        self.logger.info("TSR worker started")
        
        try:
            while not self.shutdown_flag.is_set():
                try:
                    # Wait for pause to be cleared
                    while self.pause_flag.is_set() and not self.shutdown_flag.is_set():
                        time.sleep(0.1)
                    
                    if self.shutdown_flag.is_set():
                        break
                    
                    # Get task from queue
                    task = self.tsr_queue.get(timeout=1)
                    if task is None:  # Shutdown signal
                        break
                    
                    self.logger.info(f"TSR worker processing: {task.record_id}")
                    task.status = "tsr_generating"
                    self._notify_progress(task)
                    
                    # Generate TSR
                    try:
                        task.tsr_path = task.pdf_path.replace('.pdf', '.docx').replace('/pdfs/', '/tsr/')
                        
                        # Ensure TSR directory exists
                        tsr_dir = os.path.dirname(task.tsr_path)
                        if not os.path.exists(tsr_dir):
                            os.makedirs(tsr_dir, exist_ok=True)
                        
                        # Generate TSR (this is where the AI processing happens)
                        generate_tsr_from_pdf(task.pdf_path, task.tsr_path, use_agent=self.use_agent)
                        
                        task.status = "completed"
                        task.tsr_complete_time = datetime.now()
                        self.logger.info(f"TSR completed: {task.record_id}")
                        
                    except Exception as e:
                        task.status = "failed"
                        task.error = f"TSR generation failed: {str(e)}"
                        self.logger.error(f"TSR generation failed for {task.record_id}: {e}")
                    
                    self._notify_progress(task)
                    self.tsr_queue.task_done()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"TSR worker error: {e}")
                    if 'task' in locals():
                        task.status = "failed"
                        task.error = str(e)
                        self._notify_progress(task)
                        self.tsr_queue.task_done()
        
        finally:
            self.logger.info("TSR worker stopped")
    
    def start_workers(self):
        """Start all worker threads"""
        self.logger.info(f"Starting {self.max_pdf_workers} PDF workers and {self.max_tsr_workers} TSR workers")
        
        # Start PDF workers
        for i in range(self.max_pdf_workers):
            self.pdf_executor.submit(self._pdf_worker)
        
        # Start TSR workers
        for i in range(self.max_tsr_workers):
            self.tsr_executor.submit(self._tsr_worker)
    
    def submit_tasks(self, records: List[Dict[str, Any]]) -> List[str]:
        """Submit a batch of records for processing"""
        task_ids = []
        
        for record in records:
            task_id = f"{record['sheet_name']}_{record['row_idx']}"
            
            task = PipelineTask(
                record_id=task_id,
                district_guj=record['district'],
                taluka_guj=record['taluka'],
                village_guj=record['village'],
                survey_number_guj=record['survey'],
                row_idx=record['row_idx'],
                sheet_name=record['sheet_name']
            )
            
            self.tasks[task_id] = task
            task_ids.append(task_id)
            
            # If PDF already exists, skip fetch and queue for TSR directly
            safe_survey = str(record['survey']).replace('/', '_').replace(' ', '')
            expected_pdf = os.path.join(self.output_base_dir, 'pdfs', f'Survey No.{safe_survey}.pdf')
            if os.path.exists(expected_pdf):
                task.pdf_path = expected_pdf
                task.status = 'pdf_ready'
                task.pdf_complete_time = datetime.now()
                self._notify_progress(task)
                try:
                    self.tsr_queue.put(task, timeout=10)
                    self.logger.info(f"Skipped fetch (exists), queued for TSR: {task_id}")
                except queue.Full:
                    self.logger.warning("TSR queue full; blocking enqueue to avoid losing task")
                    self.tsr_queue.put(task)
                    self.logger.info(f"Queued for TSR after wait: {task_id}")
            else:
                # Add to PDF queue (prefer waiting briefly over failing the task)
                try:
                    self.pdf_queue.put(task, timeout=10)
                    self.logger.info(f"Task queued for PDF: {task_id}")
                except queue.Full:
                    self.logger.warning("PDF queue full; blocking enqueue to avoid losing task")
                    self.pdf_queue.put(task)
                    self.logger.info(f"Task queued for PDF after wait: {task_id}")
        
        return task_ids
    
    def pause_processing(self):
        """Pause all processing"""
        self.pause_flag.set()
        self.logger.info("Processing paused")
    
    def resume_processing(self):
        """Resume processing"""
        self.pause_flag.clear()
        self.logger.info("Processing resumed")
    
    def stop_processing(self):
        """Stop all processing and clean up"""
        self.logger.info("Stopping processing...")
        self.shutdown_flag.set()
        
        # Signal shutdown to workers
        for _ in range(self.max_pdf_workers):
            try:
                self.pdf_queue.put(None, timeout=1)
            except queue.Full:
                pass
        
        for _ in range(self.max_tsr_workers):
            try:
                self.tsr_queue.put(None, timeout=1)
            except queue.Full:
                pass
        
        # Shutdown executors
        self.pdf_executor.shutdown(wait=True, timeout=30)
        self.tsr_executor.shutdown(wait=True, timeout=30)
        
        self.logger.info("Processing stopped")
    
    def get_task_status(self, task_id: str) -> Optional[PipelineTask]:
        """Get the status of a specific task"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[PipelineTask]:
        """Get all tasks"""
        return list(self.tasks.values())
    
    def get_stats(self) -> PipelineStats:
        """Get current pipeline statistics"""
        self._update_stats()
        return self.stats
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete"""
        start_time = time.time()
        
        while True:
            if timeout and (time.time() - start_time) > timeout:
                return False
            
            # Check if all tasks are completed or failed
            active_tasks = [
                t for t in self.tasks.values() 
                if t.status not in ["completed", "failed"]
            ]
            
            if not active_tasks:
                return True
            
            time.sleep(0.5)
    
    def get_results(self) -> List[ProcessResult]:
        """Get results in the same format as the original processing service"""
        results = []
        
        for task in self.tasks.values():
            result = ProcessResult(
                success=(task.status == "completed"),
                pdf_path=task.pdf_path,
                tsr_path=task.tsr_path,
                error=task.error
            )
            results.append(result)
        
        return results
