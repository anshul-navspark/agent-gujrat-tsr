import requests
import sys
import os
import json
from pypdf import PdfReader
import io

def fetch_pdf_from_api(api_url, payload, output_filename):
    """
    Fetch PDF from API endpoint and save it.
    
    Args:
        api_url: The API endpoint URL
        payload: Request payload
        output_filename: Where to save the PDF
        
    Returns:
        dict: Result with success status and metadata
    """
    try:
        print(f"Fetching PDF from {api_url}...")
        response = requests.post(api_url, json=payload, timeout=900)
        
        if response.status_code == 200:
            with open(output_filename, "wb") as f:
                f.write(response.content)
            
            # Get PDF metadata
            try:
                pdf_reader = PdfReader(io.BytesIO(response.content))
                num_pages = len(pdf_reader.pages)
                
                # Extract text from first page
                first_page_text = pdf_reader.pages[0].extract_text()[:500]
                
                return {
                    'success': True,
                    'file_size': len(response.content),
                    'num_pages': num_pages,
                    'first_page_preview': first_page_text,
                    'filename': output_filename
                }
            except Exception as e:
                return {
                    'success': True,
                    'file_size': len(response.content),
                    'error': f"Could not read PDF metadata: {e}",
                    'filename': output_filename
                }
        else:
            return {
                'success': False,
                'error': f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def compare_pdfs(local_file, cloud_file):
    """Compare two PDF files."""
    print(f"\n{'='*60}")
    print("PDF COMPARISON")
    print(f"{'='*60}\n")
    
    if not os.path.exists(local_file):
        print(f"❌ Local file not found: {local_file}")
        return
    
    if not os.path.exists(cloud_file):
        print(f"❌ Cloud file not found: {cloud_file}")
        return
    
    # Compare file sizes
    local_size = os.path.getsize(local_file)
    cloud_size = os.path.getsize(cloud_file)
    
    print(f"File Sizes:")
    print(f"  Local:  {local_size:,} bytes")
    print(f"  Cloud:  {cloud_size:,} bytes")
    print(f"  Diff:   {abs(local_size - cloud_size):,} bytes")
    
    # Compare PDF content
    try:
        local_pdf = PdfReader(local_file)
        cloud_pdf = PdfReader(cloud_file)
        
        print(f"\nPage Counts:")
        print(f"  Local:  {len(local_pdf.pages)} pages")
        print(f"  Cloud:  {len(cloud_pdf.pages)} pages")
        
        # Extract and compare text from first page
        print(f"\nFirst Page Text Comparison:")
        print(f"\n--- LOCAL (first 500 chars) ---")
        local_text = local_pdf.pages[0].extract_text()
        print(local_text[:500])
        
        print(f"\n--- CLOUD (first 500 chars) ---")
        cloud_text = cloud_pdf.pages[0].extract_text()
        print(cloud_text[:500])
        
        if local_text == cloud_text:
            print("\n✅ First page text is IDENTICAL")
        else:
            print("\n❌ First page text is DIFFERENT")
            
    except Exception as e:
        print(f"\n❌ Error comparing PDFs: {e}")

def main():
    """Main function to fetch and compare PDFs from both environments."""
    
    # Test parameters
    district = "કચ્છ"
    taluka = "અબડાસા"
    village = "ત્રંબો - 033"
    survey = "51"
    
    payload = {
        "district": district,
        "taluka": taluka,
        "village": village,
        "survey_number": survey
    }
    
    print("="*60)
    print("PDF COMPARISON TOOL - Cloud vs Local")
    print("="*60)
    print(f"\nTest Parameters:")
    print(f"  District: {district}")
    print(f"  Taluka: {taluka}")
    print(f"  Village: {village}")
    print(f"  Survey: {survey}")
    print()
    
    # Note: We're comparing the scraped PDFs, not the final DOCX
    # We need to modify the API to return the scraped PDF instead of the DOCX
    # For now, let's create a simpler approach - just check the logs
    
    print("⚠️  NOTE: This script requires a modified API endpoint that returns")
    print("    the scraped PDF instead of the final DOCX document.")
    print()
    print("    Alternative approach:")
    print("    1. Check Cloud Run logs for scraping errors")
    print("    2. Add logging to save PDFs to a debug bucket")
    print("    3. Compare the saved PDFs manually")
    print()
    print("    For now, let's check if we can access the cloud logs...")
    print()
    
    # Provide command to check logs
    print("Run this command to check Cloud Run logs:")
    print()
    print("  gcloud run services logs read gujrat-tsr-agent \\")
    print("    --region=asia-south1 \\")
    print("    --project=neon-alcove-479309-q3 \\")
    print("    --limit=200 \\")
    print("    | grep -E '(ERROR|WARNING|PDF|scraping)'")
    print()

if __name__ == "__main__":
    main()
