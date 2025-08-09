#!/usr/bin/env python3

from datetime import datetime
import json
import sys
import os

# Add the parent directory to the path to import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import process_html, get_html_updates, morph_apply, replacement_apply


def main():
    html_file_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "example",
        "luma.html",
    )

    print(f"Loading HTML from: {html_file_path}")

    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            original_html = f.read()
        print("✓ HTML loaded successfully")
    except FileNotFoundError:
        print(f"Error: Could not find {html_file_path}")
        return
    except Exception as e:
        print(f"Error loading HTML: {e}")
        return

    # Define the query
    query = 'make this say "accepted" instead of "pending approval"'
    print(f"Query: {query}")

    # Follow the same flow as routes.py
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"Run ID: {run_id}")

    try:
        # Step 1: Process HTML (remove comments, replace certain tags)
        print("\n1. Processing HTML...")
        processed_html, replacements = process_html(original_html)
        print("✓ HTML processed successfully")

        # Step 2: Get HTML updates using AI
        print("\n2. Getting HTML updates...")
        updates = get_html_updates(query, processed_html)
        print("✓ HTML updates generated")
        return

        # Step 3: Apply morphing
        print("\n3. Applying morphing...")
        edited_html = morph_apply(processed_html, updates)
        print("✓ Morphing applied")

        # Step 4: Apply replacements back
        print("\n4. Applying replacements...")
        final_html = replacement_apply(edited_html, replacements)
        print("✓ Replacements applied")
        output_file = f"output_luma_{run_id}.html"
        print(f"\n5. Writing final result to: {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_html)
        print("✓ Final HTML written successfully")

        print(f"\n🎉 Process completed successfully!")
        print(f"📄 Final HTML saved to: {output_file}")

    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
