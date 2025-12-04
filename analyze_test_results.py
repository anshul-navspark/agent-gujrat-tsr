#!/usr/bin/env python3
"""
Analyze test_parallel_local.py results and categorize errors
"""
import re
import sys
from collections import defaultdict

def analyze_log_file(log_content):
    """Parse log content and categorize results"""
    
    results = {
        'success': [],
        'errors': defaultdict(list)
    }
    
    # Patterns to match
    success_pattern = r'Success for (.+?) in ([\d.]+)s\. Saved to (.+)'
    failed_pattern = r'Failed for (.+?) with status (\d+): (.+)'
    request_failed_pattern = r'Request failed for (.+?): (.+)'
    
    for line in log_content.split('\n'):
        # Check for success
        success_match = re.search(success_pattern, line)
        if success_match:
            survey_no = success_match.group(1)
            duration = success_match.group(2)
            filename = success_match.group(3)
            results['success'].append({
                'survey_no': survey_no,
                'duration': float(duration),
                'filename': filename
            })
            continue
        
        # Check for API failures (status 500)
        failed_match = re.search(failed_pattern, line)
        if failed_match:
            survey_no = failed_match.group(1)
            status_code = failed_match.group(2)
            error_msg = failed_match.group(3)
            
            # Categorize error type
            if 'Captcha could not be solved' in error_msg:
                error_type = 'Captcha Failed'
            elif 'District not found' in error_msg:
                error_type = 'District Not Found'
            elif 'Failed to extract text from PDF' in error_msg:
                error_type = 'PDF Extraction Failed'
            elif 'Connection refused' in error_msg or 'Max retries exceeded' in error_msg:
                error_type = 'WebDriver Connection Error'
            elif 'All WebDriver initialization approaches failed' in error_msg:
                error_type = 'WebDriver Initialization Failed'
            else:
                error_type = 'Other API Error'
            
            results['errors'][error_type].append({
                'survey_no': survey_no,
                'status_code': status_code,
                'error_msg': error_msg
            })
            continue
        
        # Check for request failures (timeouts, etc)
        request_failed_match = re.search(request_failed_pattern, line)
        if request_failed_match:
            survey_no = request_failed_match.group(1)
            error_msg = request_failed_match.group(2)
            
            if 'Read timed out' in error_msg:
                error_type = 'Request Timeout'
            else:
                error_type = 'Request Failed'
            
            results['errors'][error_type].append({
                'survey_no': survey_no,
                'error_msg': error_msg
            })
    
    return results

def print_summary(results):
    """Print a formatted summary of results"""
    
    print("=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)
    
    # Success summary
    success_count = len(results['success'])
    print(f"\n✅ SUCCESSFUL: {success_count} records")
    if success_count > 0:
        avg_duration = sum(r['duration'] for r in results['success']) / success_count
        print(f"   Average duration: {avg_duration:.2f}s")
        print(f"   Survey numbers: {', '.join(r['survey_no'] for r in results['success'])}")
    
    # Error summary
    total_errors = sum(len(errors) for errors in results['errors'].values())
    print(f"\n❌ FAILED: {total_errors} records")
    
    if total_errors > 0:
        print("\nError Breakdown:")
        for error_type, errors in sorted(results['errors'].items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n  {error_type}: {len(errors)} occurrences")
            survey_nos = [e['survey_no'] for e in errors[:5]]  # Show first 5
            print(f"    Survey numbers: {', '.join(survey_nos)}")
            if len(errors) > 5:
                print(f"    ... and {len(errors) - 5} more")
            
            # Show one example error message
            print(f"    Example error: {errors[0]['error_msg'][:150]}...")
    
    print("\n" + "=" * 80)
    print(f"TOTAL PROCESSED: {success_count + total_errors}")
    print("=" * 80)

def print_recommendations(results):
    """Print recommendations for fixing errors"""
    
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    
    for error_type, errors in results['errors'].items():
        if not errors:
            continue
            
        print(f"\n🔧 {error_type} ({len(errors)} occurrences):")
        
        if error_type == 'Captcha Failed':
            print("   - This is the most common issue with web scraping")
            print("   - The captcha solver is failing to solve the captcha")
            print("   - Possible solutions:")
            print("     1. Improve captcha solving logic in anyror_refactored.py")
            print("     2. Add retry logic with delays")
            print("     3. Use a different captcha solving service")
            print("     4. Reduce parallel workers to avoid rate limiting")
        
        elif error_type == 'WebDriver Connection Error':
            print("   - Chrome/ChromeDriver is crashing or becoming unresponsive")
            print("   - Possible solutions:")
            print("     1. Reduce number of parallel workers (currently 5)")
            print("     2. Add better error handling and driver restart logic")
            print("     3. Increase system resources or close other applications")
        
        elif error_type == 'WebDriver Initialization Failed':
            print("   - Chrome/ChromeDriver compatibility issue")
            print("   - Possible solutions:")
            print("     1. Update ChromeDriver to match Chrome version")
            print("     2. Check Chrome installation")
        
        elif error_type == 'District Not Found':
            print("   - Translation or district lookup issue")
            print("   - Possible solutions:")
            print("     1. Check anyror_hierarchy.json for district mapping")
            print("     2. Verify translation is correct")
        
        elif error_type == 'PDF Extraction Failed':
            print("   - PDF processing issue")
            print("   - Possible solutions:")
            print("     1. Check PDF quality/format")
            print("     2. Improve PDF text extraction logic")
        
        elif error_type == 'Request Timeout':
            print("   - Request took longer than 300 seconds")
            print("   - Possible solutions:")
            print("     1. Increase timeout value")
            print("     2. Optimize scraping logic to be faster")
            print("     3. Check if server is overloaded")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Read from file
        with open(sys.argv[1], 'r') as f:
            log_content = f.read()
    else:
        # Read from stdin
        log_content = sys.stdin.read()
    
    results = analyze_log_file(log_content)
    print_summary(results)
    print_recommendations(results)
