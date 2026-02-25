#!/usr/bin/env python3
"""
build-walkthrough-appendix.py

Reads docs/presentations/app-walkthrough/manifest.json, generates HTML slide
sections for each persona and their screenshots, and inserts them into
docs/presentations/index.html before the closing hero slide (slide-57).

Idempotent: removes previously-inserted walkthrough slides before inserting
fresh ones, using HTML comment markers.

Usage:
    python scripts/build-walkthrough-appendix.py
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = REPO_ROOT / "docs/presentations/app-walkthrough/manifest.json"
HTML_PATH = REPO_ROOT / "docs/presentations/index.html"

# ---------------------------------------------------------------------------
# Persona descriptions
# ---------------------------------------------------------------------------
PERSONA_DESCRIPTIONS = {
    "Platform Admin": (
        "Full platform access with system administration, task mining management, "
        "and all analytical capabilities"
    ),
    "Engagement Lead": (
        "Manages engagements end-to-end with access to evidence, analysis, "
        "governance, and reporting capabilities"
    ),
    "Process Analyst": (
        "Deep analytical capabilities focused on evidence processing, conformance "
        "checking, and process discovery"
    ),
    "Client Viewer": (
        "Read-only portal access for clients to review findings, evidence status, "
        "and process models"
    ),
}

# Marker comments for idempotency.
# MARKER_START embeds the original hero slide number so it can be restored on removal.
MARKER_START_TEMPLATE = "<!-- WALKTHROUGH-APPENDIX-START hero={hero_num} -->"
MARKER_END = "<!-- WALKTHROUGH-APPENDIX-END -->"

# The hero slide comment that we insert BEFORE
HERO_COMMENT = "<!-- Slide 57: Final Hero -->"


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------

def make_divider_slide(slide_num: int) -> str:
    """Generate the Appendix divider slide."""
    return f"""
    <section id="slide-{slide_num}" class="slide slide-gradient">
      <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-align: center;">
        <div style="margin-bottom: 1.5rem;">
          <span style="display: inline-block; background: rgba(255,255,255,0.2); color: #fff; font-family: var(--font-body); font-size: 0.85rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; padding: 0.4rem 1.2rem; border-radius: 2rem; border: 1px solid rgba(255,255,255,0.35);">Appendix</span>
        </div>
        <h1 style="font-family: var(--font-heading); font-size: 3.2rem; font-weight: 700; color: #fff; margin: 0 0 1rem; letter-spacing: -0.01em; text-transform: uppercase;">Application Walkthrough</h1>
        <p style="font-family: var(--font-body); font-size: 1.2rem; color: rgba(255,255,255,0.85); max-width: 560px; margin: 0 auto 2.5rem;">Live screenshots of the KMFlow platform across four user personas — from full administrative access to client-facing read-only views.</p>
        <div style="display: flex; gap: 2rem; justify-content: center; flex-wrap: wrap;">
          <div style="background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 0.75rem 1.5rem; text-align: center;">
            <div style="font-family: var(--font-heading); font-size: 2rem; font-weight: 700; color: #fff;">4</div>
            <div style="font-family: var(--font-body); font-size: 0.8rem; color: rgba(255,255,255,0.75); text-transform: uppercase; letter-spacing: 0.08em;">Personas</div>
          </div>
          <div style="background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.25); border-radius: 8px; padding: 0.75rem 1.5rem; text-align: center;">
            <div style="font-family: var(--font-heading); font-size: 2rem; font-weight: 700; color: #fff;">59</div>
            <div style="font-family: var(--font-body); font-size: 0.8rem; color: rgba(255,255,255,0.75); text-transform: uppercase; letter-spacing: 0.08em;">Screenshots</div>
          </div>
        </div>
      </div>
      <div class="slide-footer">
        <span>Confidential</span>
        <span>KMFlow Platform</span>
        <span>Slide {slide_num}</span>
      </div>
    </section>"""


def make_persona_intro_slide(slide_num: int, persona: dict, description: str) -> str:
    """Generate a persona title/intro slide."""
    name = persona["name"]
    email = persona["email"]
    page_count = persona["pageCount"]

    # Pick an icon character per persona (simple text-based badge)
    icon_map = {
        "Platform Admin": "&#9881;",       # gear
        "Engagement Lead": "&#128197;",    # calendar (briefcase-ish)
        "Process Analyst": "&#128200;",    # chart
        "Client Viewer": "&#128065;",      # eye
    }
    icon = icon_map.get(name, "&#9679;")

    return f"""
    <section id="slide-{slide_num}" class="slide slide-dark">
      <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-align: center;">
        <div style="width: 72px; height: 72px; border-radius: 50%; background: var(--kmflow-light-blue); display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; font-size: 2rem; box-shadow: 0 4px 16px rgba(0,145,218,0.4);">
          <span>{icon}</span>
        </div>
        <div style="margin-bottom: 0.75rem;">
          <span style="display: inline-block; background: rgba(0,145,218,0.2); color: var(--kmflow-light-blue); font-family: var(--font-body); font-size: 0.8rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; padding: 0.35rem 1rem; border-radius: 2rem; border: 1px solid rgba(0,145,218,0.35);">Persona Walkthrough</span>
        </div>
        <h2 style="font-family: var(--font-heading); font-size: 2.8rem; font-weight: 700; color: #fff; margin: 0 0 1rem; text-transform: uppercase; letter-spacing: -0.01em;">{name}</h2>
        <p style="font-family: var(--font-body); font-size: 1.05rem; color: rgba(255,255,255,0.8); max-width: 520px; margin: 0 auto 2rem; line-height: 1.6;">{description}</p>
        <div style="display: flex; gap: 1.5rem; justify-content: center; margin-bottom: 1rem;">
          <div style="background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; padding: 0.65rem 1.25rem; text-align: center;">
            <div style="font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; color: var(--kmflow-light-blue);">{page_count}</div>
            <div style="font-family: var(--font-body); font-size: 0.75rem; color: rgba(255,255,255,0.6); text-transform: uppercase; letter-spacing: 0.08em;">Pages</div>
          </div>
          <div style="background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; padding: 0.65rem 1.25rem; text-align: center; display: flex; flex-direction: column; justify-content: center;">
            <div style="font-family: var(--font-body); font-size: 0.8rem; color: rgba(255,255,255,0.8); font-weight: 500;">{email}</div>
            <div style="font-family: var(--font-body); font-size: 0.7rem; color: rgba(255,255,255,0.45); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem;">Demo Account</div>
          </div>
        </div>
      </div>
      <div class="slide-footer">
        <span>Confidential</span>
        <span>KMFlow Platform</span>
        <span>Slide {slide_num}</span>
      </div>
    </section>"""


def make_screenshot_slide(slide_num: int, screenshot: dict) -> str:
    """Generate a screenshot slide for a single page."""
    title = screenshot["title"]
    path = screenshot["path"]
    filename = screenshot["filename"]
    img_src = f"app-walkthrough/{filename}"

    return f"""
    <section id="slide-{slide_num}" class="slide slide-light">
      <div style="display: flex; flex-direction: column; align-items: center; height: 100%; padding-top: 0.5rem;">
        <div style="width: 100%; margin-bottom: 1rem; text-align: center;">
          <h3 style="font-family: var(--font-heading); font-size: 1.6rem; font-weight: 700; color: var(--kmflow-dark-navy); text-transform: uppercase; letter-spacing: 0.01em; margin: 0 0 0.25rem;">{title}</h3>
          <code style="font-family: 'Courier New', monospace; font-size: 0.8rem; color: var(--kmflow-medium-blue); background: rgba(0,94,184,0.08); padding: 0.2rem 0.6rem; border-radius: 4px; border: 1px solid rgba(0,94,184,0.15);">{path}</code>
        </div>
        <div style="flex: 1; display: flex; align-items: center; justify-content: center; width: 100%; min-height: 0;">
          <img
            src="{img_src}"
            alt="{title}"
            style="max-width: 90%; max-height: 70vh; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); border: 1px solid #e0e0e0; object-fit: contain;"
          />
        </div>
      </div>
      <div class="slide-footer">
        <span>Confidential</span>
        <span>KMFlow Platform</span>
        <span>Slide {slide_num}</span>
      </div>
    </section>"""


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def build_walkthrough_html(manifest: dict, start_slide: int) -> tuple[str, int]:
    """
    Build the full HTML block to insert (without markers).
    Returns (html_string, total_slides_added).
    """
    personas = manifest["personas"]
    screenshots = manifest["screenshots"]

    # Group screenshots by persona name, preserving order
    screenshots_by_persona: dict[str, list] = {}
    for p in personas:
        screenshots_by_persona[p["name"]] = []
    for s in screenshots:
        persona_name = s["persona"]
        if persona_name in screenshots_by_persona:
            screenshots_by_persona[persona_name].append(s)

    parts = []
    current = start_slide

    # Appendix divider slide
    parts.append(make_divider_slide(current))
    current += 1

    for persona in personas:
        pname = persona["name"]
        description = PERSONA_DESCRIPTIONS.get(pname, "")

        # Persona intro slide
        parts.append(make_persona_intro_slide(current, persona, description))
        current += 1

        # Screenshot slides
        for screenshot in screenshots_by_persona[pname]:
            parts.append(make_screenshot_slide(current, screenshot))
            current += 1

    total_added = current - start_slide
    return "\n".join(parts), total_added


def remove_existing_block(html: str) -> tuple[str, int | None]:
    """Strip any previously inserted walkthrough block (between markers).

    Returns (updated_html, original_hero_num_or_None).
    If a previous block is found, also restores the hero slide number to
    the value stored in the marker comment.
    """
    # Match the start marker with optional hero= attribute
    start_pattern = re.compile(
        r"<!-- WALKTHROUGH-APPENDIX-START(?: hero=(\d+))? -->"
    )
    start_match = start_pattern.search(html)
    if not start_match:
        return html, None

    end_idx = html.find(MARKER_END)
    if end_idx == -1:
        return html, None

    original_hero_num = int(start_match.group(1)) if start_match.group(1) else None

    # Remove everything from the start marker through the end marker (inclusive)
    block_start = start_match.start()
    block_end = end_idx + len(MARKER_END)
    html = html[:block_start] + html[block_end:]

    # If the hero was renumbered, restore it
    if original_hero_num is not None:
        # Find current hero num from the last slide section
        current_hero = find_hero_slide_number(html)
        if current_hero != original_hero_num:
            # Restore comment, id, and footer span
            html = html.replace(
                f"<!-- Slide {current_hero}: Final Hero -->",
                f"<!-- Slide {original_hero_num}: Final Hero -->",
                1,
            )
            # Find the hero section via the restored comment and fix id/footer
            comment_pos = html.find(f"<!-- Slide {original_hero_num}: Final Hero -->")
            section_start = html.find("<section ", comment_pos)
            section_end = html.find("</section>", section_start) + len("</section>")
            hero_section = html[section_start:section_end]
            hero_section = hero_section.replace(
                f'id="slide-{current_hero}"',
                f'id="slide-{original_hero_num}"',
                1,
            )
            hero_section = hero_section.replace(
                f"<span>Slide {current_hero}</span>",
                f"<span>Slide {original_hero_num}</span>",
                1,
            )
            html = html[:section_start] + hero_section + html[section_end:]

    return html, original_hero_num


def find_hero_slide_number(html: str) -> int:
    """
    Find the current slide number of the hero slide by looking at the
    last <section id="slide-N"> before </main>.
    """
    # Find all slide IDs up to </main>
    main_end = html.find("</main>")
    if main_end == -1:
        raise ValueError("Could not find </main> in HTML")
    before_main = html[:main_end]
    matches = re.findall(r'<section id="slide-(\d+)"', before_main)
    if not matches:
        raise ValueError("Could not find any slide IDs in HTML")
    return int(matches[-1])


def update_hero_slide_number(html: str, old_num: int, new_num: int) -> str:
    """Renumber the hero slide from old_num to new_num.

    Uses the unique '<!-- Slide N: Final Hero -->' comment as an anchor to
    locate the hero section precisely, avoiding false matches in the newly
    inserted walkthrough slides that may also have id="slide-{old_num}".
    """
    # Step 1: Update the comment (unique anchor)
    old_comment = f"<!-- Slide {old_num}: Final Hero -->"
    new_comment = f"<!-- Slide {new_num}: Final Hero -->"
    if old_comment not in html:
        raise ValueError(f"Could not find hero comment: {old_comment}")
    html = html.replace(old_comment, new_comment, 1)

    # Step 2: Find the hero section using the (now-updated) comment as anchor,
    # then replace the id and footer span only within that section.
    comment_pos = html.find(new_comment)
    # The <section> tag follows the comment
    section_start = html.find("<section ", comment_pos)
    if section_start == -1:
        raise ValueError("Could not find <section> after hero comment")
    section_end = html.find("</section>", section_start) + len("</section>")
    hero_section = html[section_start:section_end]

    # Replace the id attribute within the hero section
    hero_section = hero_section.replace(
        f'id="slide-{old_num}"',
        f'id="slide-{new_num}"',
        1,
    )
    # Replace the footer span within the hero section
    hero_section = hero_section.replace(
        f"<span>Slide {old_num}</span>",
        f"<span>Slide {new_num}</span>",
        1,
    )

    html = html[:section_start] + hero_section + html[section_end:]
    return html


def main() -> None:
    # --- Load manifest ---
    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)
    with MANIFEST_PATH.open() as f:
        manifest = json.load(f)

    # --- Load presentation HTML ---
    if not HTML_PATH.exists():
        print(f"ERROR: index.html not found at {HTML_PATH}", file=sys.stderr)
        sys.exit(1)
    html = HTML_PATH.read_text(encoding="utf-8")

    # --- Remove any previously inserted block (idempotency) ---
    # This also restores the hero slide number if it was previously renumbered.
    html, _ = remove_existing_block(html)

    # --- Find current hero slide number (should be 57 on a clean document) ---
    hero_num = find_hero_slide_number(html)
    print(f"Current hero (closing) slide number: {hero_num}")

    # --- Build walkthrough HTML ---
    # New slides start at hero_num (inserting before current hero)
    new_slides_html, total_added = build_walkthrough_html(manifest, start_slide=hero_num)
    print(f"Slides to insert: {total_added}")

    # --- Wrap with markers (embed original hero_num for future idempotent runs) ---
    marker_start = MARKER_START_TEMPLATE.format(hero_num=hero_num)
    block = f"\n    {marker_start}\n{new_slides_html}\n    {MARKER_END}\n"

    # --- Find insertion point: just before the hero slide comment ---
    hero_comment = f"<!-- Slide {hero_num}: Final Hero -->"
    insert_idx = html.find(f"    {hero_comment}")
    if insert_idx == -1:
        # Fallback: find the hero section tag directly
        insert_idx = html.find(f'<section id="slide-{hero_num}"')
        if insert_idx == -1:
            print("ERROR: Could not find hero slide insertion point", file=sys.stderr)
            sys.exit(1)

    # --- Insert the block ---
    html = html[:insert_idx] + block + "\n    " + html[insert_idx:]

    # --- Renumber hero slide ---
    new_hero_num = hero_num + total_added
    html = update_hero_slide_number(html, hero_num, new_hero_num)
    print(f"Hero slide renumbered: {hero_num} -> {new_hero_num}")

    # --- Write back ---
    HTML_PATH.write_text(html, encoding="utf-8")

    total_slides = new_hero_num
    print(f"\nDone.")
    print(f"  Slides added: {total_added}")
    print(f"  New total slide count: {total_slides}")
    print(f"  New hero (closing) slide: {new_hero_num}")
    print(f"  Output: {HTML_PATH}")


if __name__ == "__main__":
    main()
