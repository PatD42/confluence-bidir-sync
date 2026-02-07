"""End-to-end tests for Confluence API integration.

These tests validate the complete journeys (fetch, push) using a real
Confluence instance. They require test credentials in .env.test file.

Test Coverage:
- Fetch Journey: fetch page → convert to markdown → validate output
- Push Journey: convert markdown → update/create page → verify on Confluence

Future epics will extend these tests:
- Epic 02: Add local file I/O to journeys
- Epic 03: Add git merge integration
- Epic 04: Add section parsing
- Epic 05: Add surgical section updates
"""
