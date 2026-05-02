"""Site package — Concern 3B: SITE BUILD outport adapter.

Entry point: src.site.build
Reads ProcessedItem records from data/processed/; computes trend metrics;
writes docs/data/*.json for GitHub Pages.
Must not import fetchers or pipeline stages.
"""
