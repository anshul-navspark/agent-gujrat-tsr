# Performance Optimization Suggestions for Gujarat TSR Agent

## Executive Summary

Current processing time: **~86 seconds per record** (57 records = ~1 hour 16 minutes total)

**Estimated improvement potential: 50-70% reduction in total processing time**

---

## Current Bottlenecks Identified

### 1. **Sequential Processing** (CRITICAL)
- **Current**: Processing one record at a time
- **Impact**: No parallelization of independent operations
- **Location**: `bhuj_solar_processor.py` lines 615-626

### 2. **Browser Instance Management** (HIGH)
- **Current**: Creating/destroying browser for each record
- **Impact**: ~5-10 seconds overhead per record
- **Location**: `anyror_refactored.py` WebDriverManager class

### 3. **Multiple AI API Calls** (HIGH)
- **Current**: 3-5 separate Gemini API calls per record
  - CAPTCHA solving (1 call)
  - Land details extraction (1 call)
  - Entry details extraction (1-3 calls depending on entries)
- **Impact**: Network latency + API processing time
- **Location**: Multiple files in `tsr_generator/extractors/`

### 4. **ChromeDriver Cache Cleaning** (MEDIUM)
- **Current**: Cache cleaned before each record
- **Impact**: Re-downloading ChromeDriver repeatedly
- **Location**: `anyror_refactored.py` lines 256-277

---

## Optimization Strategies

## 🚀 Quick Wins (Easy to Implement, High Impact)

### 1. Enable Parallel PDF Fetching
**Estimated Time Savings: 40-50%**

The code already has parallel processing support but it's disabled by default.

**Implementation:**
```bash
# Use the existing --no-sequential flag
python bhuj_solar_processor.py \
  --excel-file "Bhuj Solar Land Survey List.xlsx" \
  --no-sequential \
  --max-workers 3
```

**Why 3 workers?**
- Each worker needs a separate browser instance
- Too many workers = memory issues + website rate limiting
- 3-4 workers is optimal for this use case

**Code Location**: `bhuj_solar_processor.py` lines 597-614

**Risks**:
- Potential website rate limiting (mitigate with delays)
- Higher memory usage
- More complex error handling

---

### 2. Reuse Browser Instances
**Estimated Time Savings: 10-15%**

**Current Problem:**
```python
# Each record creates a new browser
scraper = AnyRoRScraper(headless=True, logger=logger)
# ... fetch record ...
scraper.web_driver_manager.close()  # Destroys browser
```

**Proposed Solution:**
Create a browser pool that reuses instances across records.

**Implementation:**
```python
class BrowserPool:
    def __init__(self, pool_size=3):
        self.pool = Queue(maxsize=pool_size)
        for _ in range(pool_size):
            scraper = AnyRoRScraper(headless=True)
            self.pool.put(scraper)
    
    def get_scraper(self):
        return self.pool.get()
    
    def return_scraper(self, scraper):
        # Reset scraper state
        scraper.driver.delete_all_cookies()
        self.pool.put(scraper)
    
    def cleanup(self):
        while not self.pool.empty():
            scraper = self.pool.get()
            scraper.web_driver_manager.close()
```

**Where to Add**: New file `browser_pool.py` or in `anyror_refactored.py`

---

### 3. Disable Unnecessary Cache Cleaning
**Estimated Time Savings: 5-10%**

**Current Problem:**
```python
# Lines 392-426 in anyror_refactored.py
def _approach_clean_cache_and_auto_manager(self, chrome_options):
    # Removes chromedriver cache EVERY time
    self._clean_chromedriver_cache()
```

**Proposed Solution:**
```python
# Only clean cache once at startup, not for every record
# In bhuj_solar_processor.py main():
if not args.no_cleanup:
    wdm = WebDriverManager()
    wdm._clean_chromedriver_cache()  # Once at start
    
# Then disable it in the loop
# Set a global flag or pass parameter to skip cache cleaning
```

**Where to Modify**: 
- `bhuj_solar_processor.py` lines 887-896
- `anyror_refactored.py` lines 392-426

---

## 🎯 Medium Effort Optimizations

### 4. Batch AI API Calls
**Estimated Time Savings: 15-20%**

**Current Problem:**
Each TSR generation makes 3-5 separate API calls to Gemini:
1. CAPTCHA solving
2. Land details extraction
3. Entry details extraction (multiple calls)

**Proposed Solution:**
Use Gemini's batch API or combine prompts where possible.

**Implementation:**
```python
def extract_all_details_batch(pdf_text, captcha_image=None):
    """Single API call to extract all information"""
    
    prompt = f"""
    Analyze this land record and extract:
    1. Land details (village, taluka, district, survey number, area, owner)
    2. All entry details (entry numbers, dates, types, parties)
    3. Any findings or observations
    
    PDF Text:
    {pdf_text}
    
    Return as structured JSON with sections: land_details, entries, findings
    """
    
    # Single API call instead of 3-5
    response = llm.invoke(prompt)
    return parse_combined_response(response)
```

**Where to Add**: New file `tsr_generator/extractors/batch_extractor.py`

**Benefits**:
- Reduced network latency
- Lower API costs
- Faster processing

---

### 5. Implement Caching for Repeated Lookups
**Estimated Time Savings: 5-10%**

**Current Problem:**
Same villages/talukas/districts are looked up repeatedly.

**Proposed Solution:**
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def translate_to_gujarati_cached(text, translation_type):
    """Cache translation lookups"""
    if translation_type == 'district':
        return DISTRICT_TRANSLATIONS.get(text, text)
    elif translation_type == 'taluka':
        return TALUKA_TRANSLATIONS.get(text, text)
    # ... etc
```

**Where to Modify**: `bhuj_solar_processor.py` lines 206-223

---

### 6. Optimize CAPTCHA Solving
**Estimated Time Savings: 3-5%**

**Current Approach:**
- Download CAPTCHA image
- Send to Gemini API
- Wait for response

**Proposed Optimization:**
```python
# Pre-warm the CAPTCHA solver
class CaptchaSolverPool:
    def __init__(self, pool_size=3):
        self.solvers = [CaptchaSolver() for _ in range(pool_size)]
        self.current = 0
    
    def solve(self, image_data):
        # Round-robin across multiple solver instances
        solver = self.solvers[self.current]
        self.current = (self.current + 1) % len(self.solvers)
        return solver.solve(image_data)
```

**Where to Add**: `anyror_refactored.py` near CaptchaSolver class

---

## 🔬 Advanced Optimizations

### 7. Implement Async/Await for I/O Operations
**Estimated Time Savings: 20-30%**

**Current Problem:**
Synchronous I/O blocks execution during:
- API calls
- File I/O
- Network requests

**Proposed Solution:**
Convert to async/await pattern:

```python
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI

async def fetch_land_record_async(district, taluka, village, survey):
    """Async version of land record fetching"""
    # Use async Selenium or Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # ... async operations ...

async def generate_tsr_async(pdf_path, output_path):
    """Async TSR generation"""
    # Parallel execution of independent tasks
    land_task = asyncio.create_task(extract_land_details_async(pdf_text))
    entry_task = asyncio.create_task(extract_entry_details_async(pdf_text))
    findings_task = asyncio.create_task(generate_findings_async(pdf_text))
    
    # Wait for all to complete
    land_details, entries, findings = await asyncio.gather(
        land_task, entry_task, findings_task
    )
```

**Where to Implement**: 
- New async versions of extractors
- Requires significant refactoring

**Benefits**:
- True parallelism for I/O operations
- Better resource utilization
- Faster overall processing

---

### 8. Use Playwright Instead of Selenium
**Estimated Time Savings: 10-15%**

**Why Playwright?**
- Faster than Selenium
- Better async support
- More reliable
- Built-in auto-waiting

**Implementation:**
```python
from playwright.async_api import async_playwright

async def fetch_with_playwright(district, taluka, village, survey):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Navigate and interact
        await page.goto('https://anyror.gujarat.gov.in/...')
        await page.select_option('#district', district)
        # ... etc
```

**Where to Implement**: New file `anyror_playwright.py`

---

### 9. Pre-fetch and Queue Processing
**Estimated Time Savings: 15-20%**

**Concept:**
Separate PDF fetching from TSR generation into two parallel pipelines.

**Implementation:**
```python
from queue import Queue
from threading import Thread

def pipeline_processor(excel_file):
    pdf_queue = Queue(maxsize=10)
    tsr_queue = Queue(maxsize=10)
    
    # Pipeline stage 1: Fetch PDFs
    def pdf_fetcher():
        for row in data_df.iterrows():
            pdf_path = fetch_land_record(row)
            pdf_queue.put((row, pdf_path))
    
    # Pipeline stage 2: Generate TSRs
    def tsr_generator():
        while True:
            row, pdf_path = pdf_queue.get()
            if pdf_path is None:
                break
            generate_tsr_from_pdf(pdf_path, output_path)
            tsr_queue.put(output_path)
    
    # Start both pipelines
    Thread(target=pdf_fetcher).start()
    Thread(target=tsr_generator).start()
```

**Where to Add**: New file `pipeline_processor.py`

---

## 📊 Recommended Implementation Plan

### Phase 1: Immediate (1-2 hours)
1. ✅ Enable parallel processing (`--no-sequential --max-workers 3`)
2. ✅ Disable cache cleaning per record
3. ✅ Add caching for translations

**Expected Improvement: 50% reduction** (86s → 43s per record)

### Phase 2: Short-term (1-2 days)
4. Implement browser pool
5. Batch AI API calls
6. Optimize CAPTCHA solving

**Expected Improvement: 60% reduction** (86s → 34s per record)

### Phase 3: Long-term (1 week)
7. Convert to async/await
8. Implement Playwright
9. Pipeline processing

**Expected Improvement: 70% reduction** (86s → 26s per record)

---

## 🎯 Quick Start: Run with Optimizations Now

```bash
# Immediate optimization (no code changes needed)
python bhuj_solar_processor.py \
  --excel-file "Bhuj Solar Land Survey List.xlsx" \
  --no-sequential \
  --max-workers 3 \
  --no-cleanup

# This should reduce processing time from 1h 16m to ~38 minutes
```

---

## 📈 Performance Metrics to Track

1. **Per-record processing time**
   - Current: ~86 seconds
   - Target: <30 seconds

2. **API call count**
   - Current: 3-5 calls per record
   - Target: 1-2 calls per record

3. **Browser initialization time**
   - Current: ~5-10 seconds per record
   - Target: <1 second (with pooling)

4. **Memory usage**
   - Monitor with parallel processing
   - Target: <4GB total

---

## ⚠️ Risks and Mitigation

### Risk 1: Website Rate Limiting
**Mitigation:**
- Add delays between requests
- Limit max workers to 3-4
- Implement exponential backoff

### Risk 2: Memory Issues
**Mitigation:**
- Monitor memory usage
- Limit browser pool size
- Process in batches

### Risk 3: API Quota Limits
**Mitigation:**
- Implement request throttling
- Use caching aggressively
- Consider API quota monitoring

---

## 💡 Additional Recommendations

1. **Monitoring and Logging**
   - Add performance metrics logging
   - Track success/failure rates
   - Monitor API usage

2. **Error Recovery**
   - Implement checkpoint/resume functionality
   - Save progress after each successful record
   - Add retry logic with exponential backoff

3. **Resource Management**
   - Implement graceful shutdown
   - Clean up resources properly
   - Handle interruptions (Ctrl+C)

---

## 📝 Code Examples

### Example 1: Enable Parallel Processing (Immediate)

```python
# Current command
python bhuj_solar_processor.py --excel-file "Bhuj Solar Land Survey List.xlsx"

# Optimized command
python bhuj_solar_processor.py \
  --excel-file "Bhuj Solar Land Survey List.xlsx" \
  --no-sequential \
  --max-workers 3 \
  --no-cleanup
```

### Example 2: Browser Pool Implementation

```python
# File: browser_pool.py
from queue import Queue
from anyror_refactored import AnyRoRScraper
import logging

class BrowserPool:
    def __init__(self, pool_size=3, headless=True):
        self.pool = Queue(maxsize=pool_size)
        self.logger = logging.getLogger(__name__)
        
        for i in range(pool_size):
            try:
                scraper = AnyRoRScraper(headless=headless)
                self.pool.put(scraper)
                self.logger.info(f"Initialized browser {i+1}/{pool_size}")
            except Exception as e:
                self.logger.error(f"Failed to initialize browser {i+1}: {e}")
    
    def acquire(self):
        """Get a browser from the pool"""
        return self.pool.get()
    
    def release(self, scraper):
        """Return a browser to the pool"""
        try:
            # Clear cookies and reset state
            if scraper.driver:
                scraper.driver.delete_all_cookies()
            self.pool.put(scraper)
        except Exception as e:
            self.logger.error(f"Error releasing browser: {e}")
            # Create a new one if the old one is broken
            try:
                new_scraper = AnyRoRScraper(headless=True)
                self.pool.put(new_scraper)
            except:
                pass
    
    def cleanup(self):
        """Clean up all browsers"""
        while not self.pool.empty():
            try:
                scraper = self.pool.get_nowait()
                scraper.web_driver_manager.close()
            except:
                pass

# Usage in bhuj_solar_processor.py
browser_pool = BrowserPool(pool_size=3)

def process_single_row_with_pool(row, args, logger, browser_pool):
    scraper = browser_pool.acquire()
    try:
        # ... process record ...
        result = scraper.fetch_land_record(...)
        return result
    finally:
        browser_pool.release(scraper)
```

### Example 3: Batch API Calls

```python
# File: tsr_generator/extractors/batch_extractor.py
import os
from langchain_google_genai import ChatGoogleGenerativeAI
import json

def extract_all_tsr_data_batch(pdf_text):
    """Extract all TSR data in a single API call"""
    
    llm = ChatGoogleGenerativeAI(
        model=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.5-flash'),
        google_api_key=os.getenv('GEMINI_API_KEY', ''),
        temperature=0
    )
    
    prompt = f"""
    Analyze this Gujarat land record document and extract ALL information in a single response.
    
    Extract:
    1. LAND DETAILS: village_name, taluka_name, district_name, survey_number, total_area, nature_of_land, owner
    2. ENTRY DETAILS: For each entry, extract entry_number, date, type, parties, details
    3. FINDINGS: Any observations or findings
    
    Return ONLY a JSON object with this structure:
    {{
        "land_details": {{...}},
        "entries": [...],
        "findings": [...]
    }}
    
    Document Text:
    {pdf_text[:8000]}  # Limit to avoid token limits
    """
    
    response = llm.invoke(prompt)
    
    # Parse response
    try:
        data = json.loads(response.content)
        return data
    except:
        # Fallback to individual extraction
        return None
```

---

## 🔍 Profiling Recommendations

To identify exact bottlenecks, add profiling:

```python
import cProfile
import pstats
from pstats import SortKey

# Profile a single record
profiler = cProfile.Profile()
profiler.enable()

process_single_row(row, args, logger)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats(SortKey.CUMULATIVE)
stats.print_stats(20)  # Top 20 slowest functions
```

---

## Summary

**Current Performance**: 86 seconds/record × 57 records = 81.5 minutes

**With Phase 1 Optimizations**: 43 seconds/record × 57 records = **41 minutes** (50% improvement)

**With Phase 2 Optimizations**: 34 seconds/record × 57 records = **32 minutes** (60% improvement)

**With Phase 3 Optimizations**: 26 seconds/record × 57 records = **25 minutes** (70% improvement)

**Start with Phase 1** - it requires zero code changes, just command-line flags!
