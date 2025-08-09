#!/usr/bin/env python3
"""
Test script to identify what's causing the visual malformation (empty boxes, broken layout)
"""

from datetime import datetime
import json
import sys
import os

# Add the parent directory to the path to import from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils import process_html, morph_apply, replacement_apply
from src.llm import forward
from src.prompt import prompt
from src.logger import get_logger

logger = get_logger(__name__)


def analyze_html_structure(html_content, label):
    """Analyze HTML structure for issues that could cause visual malformation"""
    print(f"\n🔍 {label} Analysis:")

    # Look for empty anchor tags
    empty_company_anchors = html_content.count(
        '<a class="!py-4 _company_i9oky_355"></a>'
    )
    total_company_anchors = html_content.count('<a class="!py-4 _company_i9oky_355"')

    # Look for broken image structure
    img_tags = html_content.count("<img")
    broken_img_divs = html_content.count(
        '<div class="flex w-20 shrink-0 grow-0 basis-20 items-center pr-4"></div>'
    )

    # Look for nested anchor issues
    nested_anchors = html_content.count(
        '<a class="!py-4 _company_i9oky_355">\n            <div class="relative flex w-full items-center justify-start">\n                <div class="flex w-20 shrink-0 grow-0 basis-20 items-center pr-4"><a'
    )

    print(
        f"  📊 Company anchors: {total_company_anchors} total, {empty_company_anchors} empty"
    )
    print(f"  🖼️  Image tags: {img_tags}")
    print(f"  💔 Broken image containers: {broken_img_divs}")
    print(f"  🔗 Nested anchor issues: {nested_anchors}")

    # Sample a few company entries to see structure
    import re

    company_pattern = r'<a class="!py-4 _company_i9oky_355"[^>]*>.*?</a>'
    companies = re.findall(company_pattern, html_content, re.DOTALL)

    print(f"  📝 Found {len(companies)} complete company entries")

    if companies:
        print(f"  🔍 First company structure (first 200 chars):")
        print(f"     {companies[0][:200]}...")

    return {
        "total_company_anchors": total_company_anchors,
        "empty_company_anchors": empty_company_anchors,
        "img_tags": img_tags,
        "broken_img_divs": broken_img_divs,
        "nested_anchors": nested_anchors,
        "complete_companies": len(companies),
    }


def test_morphing_issue():
    """Test to identify what step is causing the visual malformation"""

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"🚀 Starting malformation analysis with Run ID: {run_id}")

    # Load the correct HTML
    try:
        with open("trajectories/correct.html", "r", encoding="utf-8") as f:
            original_html = f.read()
    except FileNotFoundError:
        print("❌ Error: trajectories/correct.html not found")
        return

    print("✅ Loaded correct.html")

    # Step 1: Analyze original structure
    original_stats = analyze_html_structure(original_html, "ORIGINAL (correct.html)")

    # Step 2: Process HTML (remove comments, replace complex tags)
    print("\n🔄 Step 2: Processing HTML...")
    processed_html, replacements = process_html(original_html)

    with open(f"debug_step2_processed_{run_id}.html", "w", encoding="utf-8") as f:
        f.write(processed_html)

    processed_stats = analyze_html_structure(
        processed_html, "PROCESSED (after process_html)"
    )

    # Step 3: Generate LLM edits
    print("\n🔄 Step 3: Generating LLM edits...")

    query = "add a new company at the top called google with all the needed info"
    formatted_prompt = prompt.replace("{FILE}", processed_html).replace(
        "{QUERY}", query
    )

    generation = forward(formatted_prompt, None, "openai")

    if generation.status != "success":
        print(f"❌ LLM generation failed: {generation.message}")
        return

    print(f"✅ LLM generated edits ({len(generation.edits)} chars)")

    with open(f"debug_step3_edits_{run_id}.html", "w", encoding="utf-8") as f:
        f.write(generation.edits)

    # Step 4: Apply morphing
    print("\n🔄 Step 4: Applying morphing...")
    try:
        morphed_html = morph_apply(processed_html, generation.edits)

        with open(f"debug_step4_morphed_{run_id}.html", "w", encoding="utf-8") as f:
            f.write(morphed_html)

        morphed_stats = analyze_html_structure(
            morphed_html, "MORPHED (after morph_apply)"
        )

    except Exception as e:
        print(f"❌ Morphing failed: {e}")
        return

    # Step 5: Apply replacements
    print("\n🔄 Step 5: Applying replacements...")
    final_html = replacement_apply(morphed_html, replacements)

    with open(f"debug_step5_final_{run_id}.html", "w", encoding="utf-8") as f:
        f.write(final_html)

    final_stats = analyze_html_structure(final_html, "FINAL (after replacement_apply)")

    # Analysis summary
    print("\n" + "=" * 80)
    print("📊 MALFORMATION ANALYSIS SUMMARY")
    print("=" * 80)

    steps = [
        ("Original", original_stats),
        ("Processed", processed_stats),
        ("Morphed", morphed_stats),
        ("Final", final_stats),
    ]

    print(
        f"{'Step':<12} {'Anchors':<8} {'Empty':<6} {'Images':<8} {'Broken':<8} {'Complete':<10}"
    )
    print("-" * 60)

    for step_name, stats in steps:
        print(
            f"{step_name:<12} {stats['total_company_anchors']:<8} {stats['empty_company_anchors']:<6} {stats['img_tags']:<8} {stats['broken_img_divs']:<8} {stats['complete_companies']:<10}"
        )

    # Identify where the problem occurs
    print("\n🎯 PROBLEM IDENTIFICATION:")
    for i, (step_name, stats) in enumerate(steps[1:], 1):
        prev_stats = steps[i - 1][1]

        if stats["empty_company_anchors"] > prev_stats["empty_company_anchors"]:
            print(
                f"❌ ISSUE DETECTED: {step_name} step created {stats['empty_company_anchors'] - prev_stats['empty_company_anchors']} empty anchors"
            )

        if stats["img_tags"] < prev_stats["img_tags"]:
            print(
                f"❌ ISSUE DETECTED: {step_name} step lost {prev_stats['img_tags'] - stats['img_tags']} image tags"
            )

        if stats["complete_companies"] < prev_stats["complete_companies"]:
            print(
                f"❌ ISSUE DETECTED: {step_name} step broke {prev_stats['complete_companies'] - stats['complete_companies']} company structures"
            )

    print(f"\n✅ Analysis complete. Debug files saved with run ID: {run_id}")


if __name__ == "__main__":
    test_morphing_issue()
