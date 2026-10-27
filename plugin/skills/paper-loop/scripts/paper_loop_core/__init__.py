"""Paper Loop core for Claude skills: worksheets in, marked PDFs out, with Claude doing the marking.

Uses only what Claude's code sandboxes ship with (numpy, scipy, Pillow, pypdfium2, reportlab), so it
runs in Cowork, claude.ai, and Claude Code without installing anything. Reads and writes the same
layout.json, key.json, ingest.json, and feedback.json as the Paper Loop CLI.
"""
