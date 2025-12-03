#!/usr/bin/env python3
"""
Test script for TSR Tools MCP Server

This script tests the MCP server tools individually without requiring
a full MCP client connection.
"""

import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools import fetch_pdf, analyze_pdf, generate_tsr, batch_process


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(result_json):
    """Pretty print JSON result."""
    try:
        result = json.loads(result_json)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result
    except json.JSONDecodeError:
        print(result_json)
        return None


def test_tool_imports():
    """Test that all tools can be imported."""
    print_section("Testing Tool Imports")

    tools = [
        ("fetch_pdf", fetch_pdf),
        ("analyze_pdf", analyze_pdf),
        ("generate_tsr", generate_tsr),
        ("batch_process", batch_process)
    ]

    for name, module in tools:
        if hasattr(module, 'execute'):
            print(f"✓ {name}.execute() found")
        else:
            print(f"✗ {name}.execute() NOT found")
            return False

    print("\n✓ All tool imports successful")
    return True


def test_fetch_pdf_validation():
    """Test fetch_pdf tool with invalid inputs."""
    print_section("Testing fetch_pdf Validation")

    # Test with invalid district (should fail translation)
    print("\nTest 1: Invalid district name")
    result_json = fetch_pdf.execute(
        district="InvalidDistrict",
        taluka="Bhuj",
        village="Trambo",
        survey_number="51"
    )
    result = print_result(result_json)

    if result and not result.get("success"):
        print("✓ Validation working - rejected invalid district")
        return True
    else:
        print("✗ Validation failed - should reject invalid district")
        return False


def test_analyze_pdf_validation():
    """Test analyze_pdf tool with invalid inputs."""
    print_section("Testing analyze_pdf Validation")

    # Test with non-existent PDF
    print("\nTest: Non-existent PDF file")
    result_json = analyze_pdf.execute(
        pdf_path="/nonexistent/file.pdf"
    )
    result = print_result(result_json)

    if result and not result.get("success"):
        print("✓ Validation working - rejected non-existent file")
        return True
    else:
        print("✗ Validation failed - should reject non-existent file")
        return False


def test_generate_tsr_validation():
    """Test generate_tsr tool with invalid inputs."""
    print_section("Testing generate_tsr Validation")

    # Test with non-existent PDF
    print("\nTest: Non-existent PDF file")
    result_json = generate_tsr.execute(
        pdf_path="/nonexistent/file.pdf"
    )
    result = print_result(result_json)

    if result and not result.get("success"):
        print("✓ Validation working - rejected non-existent file")
        return True
    else:
        print("✗ Validation failed - should reject non-existent file")
        return False


def test_batch_process_validation():
    """Test batch_process tool with invalid inputs."""
    print_section("Testing batch_process Validation")

    # Test with non-existent Excel file
    print("\nTest: Non-existent Excel file")
    result_json = batch_process.execute(
        excel_path="/nonexistent/file.xlsx"
    )
    result = print_result(result_json)

    if result and not result.get("success"):
        print("✓ Validation working - rejected non-existent file")
        return True
    else:
        print("✗ Validation failed - should reject non-existent file")
        return False


def test_full_workflow():
    """Test full workflow if sample data exists."""
    print_section("Testing Full Workflow (Optional)")

    # Check if we have sample PDFs
    sample_paths = [
        "output/pdfs",
        "outputs/pdfs",
        "test_data"
    ]

    sample_pdf = None
    for path in sample_paths:
        if os.path.exists(path):
            for file in os.listdir(path):
                if file.endswith('.pdf'):
                    sample_pdf = os.path.join(path, file)
                    break
        if sample_pdf:
            break

    if not sample_pdf:
        print("⊘ No sample PDFs found - skipping full workflow test")
        print("  (This is OK - validation tests passed)")
        return True

    print(f"\nFound sample PDF: {sample_pdf}")

    # Test analyze
    print("\nAnalyzing PDF...")
    result_json = analyze_pdf.execute(
        pdf_path=sample_pdf,
        extract_land=True,
        extract_entries=True
    )
    result = print_result(result_json)

    if not result or not result.get("success"):
        print("✗ Analysis failed")
        return False

    print("✓ Analysis successful")

    # Test TSR generation
    print("\nGenerating TSR...")
    tsr_output = sample_pdf.replace('.pdf', '_TEST_TSR.docx')
    result_json = generate_tsr.execute(
        pdf_path=sample_pdf,
        output_path=tsr_output
    )
    result = print_result(result_json)

    if not result or not result.get("success"):
        print("✗ TSR generation failed")
        return False

    if os.path.exists(tsr_output):
        print(f"✓ TSR generated successfully: {tsr_output}")
        # Clean up test file
        try:
            os.remove(tsr_output)
            print("  (Test file cleaned up)")
        except:
            pass
        return True
    else:
        print("✗ TSR file not created")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  TSR Tools MCP Server - Test Suite")
    print("=" * 60)

    tests = [
        ("Tool Imports", test_tool_imports),
        ("fetch_pdf Validation", test_fetch_pdf_validation),
        ("analyze_pdf Validation", test_analyze_pdf_validation),
        ("generate_tsr Validation", test_generate_tsr_validation),
        ("batch_process Validation", test_batch_process_validation),
        ("Full Workflow", test_full_workflow)
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n✗ Test '{test_name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    print_section("Test Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{status}  {test_name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! MCP server is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
