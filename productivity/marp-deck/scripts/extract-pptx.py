#!/usr/bin/env python3
"""
Extract all content from a PowerPoint file (.pptx) for conversion into a
Marp Markdown deck.

Writes two things into <output_dir>:
  - extracted-slides.json : structured text/images/notes per slide
  - assets/               : every embedded image, ready to reference with
                            relative paths (./assets/...) from the Markdown

Usage:
    python extract-pptx.py <input.pptx> [output_dir]

Requires: pip install python-pptx

Adapted from frontend-slides (zarazhangrui/frontend-slides, MIT). The original
emitted content for an HTML pipeline; this version is unchanged in extraction
logic but is documented for the Marp/Markdown flow, where images are referenced
with relative paths and speaker notes become HTML comments in the .md.
"""

import json
import os
import sys

try:
    from pptx import Presentation
except ImportError:
    sys.exit("python-pptx is required. Install it with: pip install python-pptx")


def extract_pptx(file_path, output_dir="."):
    """Extract slides (title, text, images, notes) from a .pptx file."""
    prs = Presentation(file_path)
    slides_data = []

    assets_dir = os.path.join(output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    for slide_num, slide in enumerate(prs.slides):
        slide_data = {
            "number": slide_num + 1,
            "title": "",
            "content": [],
            "images": [],
            "notes": "",
        }

        for shape in slide.shapes:
            if shape.has_text_frame:
                if shape == slide.shapes.title:
                    slide_data["title"] = shape.text
                else:
                    text = shape.text.strip()
                    if text:
                        slide_data["content"].append({"type": "text", "content": text})

            if shape.shape_type == 13:  # Picture
                image = shape.image
                image_name = (
                    f"slide{slide_num + 1}_img{len(slide_data['images']) + 1}.{image.ext}"
                )
                image_path = os.path.join(assets_dir, image_name)
                with open(image_path, "wb") as f:
                    f.write(image.blob)
                slide_data["images"].append(
                    {
                        "path": f"./assets/{image_name}",
                        "width": shape.width,
                        "height": shape.height,
                    }
                )

        if slide.has_notes_slide:
            slide_data["notes"] = slide.notes_slide.notes_text_frame.text.strip()

        slides_data.append(slide_data)

    return slides_data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python extract-pptx.py <input.pptx> [output_dir]")

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    os.makedirs(output_dir, exist_ok=True)

    slides = extract_pptx(input_file, output_dir)

    out_path = os.path.join(output_dir, "extracted-slides.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(slides, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(slides)} slides to {out_path}")
    for s in slides:
        print(f"  Slide {s['number']}: {s['title'] or '(no title)'} "
              f"— {len(s['images'])} image(s), {len(s['content'])} text block(s)")
    print("\nNext: hand extracted-slides.json to the skill to author the Marp .md "
          "(images via relative ./assets/ paths, notes as <!-- HTML comments -->).")
