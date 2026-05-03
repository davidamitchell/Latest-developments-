"""Digest package — Concern 3A: EMAIL DIGEST outport adapter.

Entry point: src.digest.send
Reads ProcessedItem records from data/processed/; sends email; archives history.
Must not import fetchers or pipeline stages.
"""
