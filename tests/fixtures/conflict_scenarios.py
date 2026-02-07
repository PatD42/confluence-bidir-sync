"""Conflict scenario fixtures for testing git-based conflict detection.

These fixtures represent different conflict scenarios used for:
- Testing conflict detection logic
- Testing auto-merge vs manual merge decisions
- Testing merge tool integration
- Creating reproducible test cases for E2E tests

Each scenario includes base, local, and remote versions of markdown content.
"""

# Scenario 1: Overlapping changes in same section (requires manual merge)
CONFLICT_SCENARIO_1 = {
    "base": """# Getting Started

## Installation

Install via pip:

```bash
pip install myapp
```

## Configuration

Set up your config file in `~/.myapp/config.yaml`.
""",
    "local": """# Getting Started

## Installation

Install via pip (with extras):

```bash
pip install myapp[all]
```

## Configuration

Set up your config file in `~/.myapp/config.yaml`.
""",
    "remote": """# Getting Started

## Installation

Install via poetry:

```bash
poetry add myapp
```

## Configuration

Set up your config file in `~/.myapp/config.yaml`.
"""
}

# Scenario 2: Non-overlapping changes (auto-mergeable)
CONFLICT_SCENARIO_2 = {
    "base": """# Documentation

## Section A

Content A original.

## Section B

Content B original.

## Section C

Content C original.
""",
    "local": """# Documentation

## Section A

Content A modified locally.

## Section B

Content B original.

## Section C

Content C original.
""",
    "remote": """# Documentation

## Section A

Content A original.

## Section B

Content B original.

## Section C

Content C modified remotely.
"""
}

# Scenario 3: Identical changes (no conflict)
CONFLICT_SCENARIO_3 = {
    "base": """# README

## Overview

This is the original overview.

## Features

- Feature 1
- Feature 2
""",
    "local": """# README

## Overview

This is the updated overview.

## Features

- Feature 1
- Feature 2
- Feature 3
""",
    "remote": """# README

## Overview

This is the updated overview.

## Features

- Feature 1
- Feature 2
- Feature 3
"""
}

# Scenario 4: Complex multi-section conflicts
CONFLICT_SCENARIO_4 = {
    "base": """# API Reference

## Authentication

Use API key authentication.

## Endpoints

### GET /users

Returns list of users.

### POST /users

Creates a new user.

## Rate Limiting

100 requests per minute.
""",
    "local": """# API Reference

## Authentication

Use OAuth 2.0 authentication.

## Endpoints

### GET /users

Returns paginated list of users.

### POST /users

Creates a new user.

### DELETE /users/:id

Deletes a user.

## Rate Limiting

100 requests per minute.
""",
    "remote": """# API Reference

## Authentication

Use JWT authentication.

## Endpoints

### GET /users

Returns list of users with filtering.

### POST /users

Creates a new user with validation.

## Rate Limiting

200 requests per minute.
"""
}

# Scenario 5: Table modifications (conflicting)
CONFLICT_SCENARIO_5 = {
    "base": """# Data Schema

## User Table

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| name | VARCHAR | User name |
| email | VARCHAR | Email address |

## Notes

Schema version 1.0
""",
    "local": """# Data Schema

## User Table

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| name | VARCHAR | User name |
| email | VARCHAR | Email address |
| created_at | TIMESTAMP | Creation date |

## Notes

Schema version 1.1
""",
    "remote": """# Data Schema

## User Table

| Column | Type | Description |
|--------|------|-------------|
| id | INT | Primary key |
| username | VARCHAR | User name |
| email | VARCHAR | Email address |
| status | ENUM | Account status |

## Notes

Schema version 1.1
"""
}

# Scenario 6: Code block modifications (conflicting)
CONFLICT_SCENARIO_6 = {
    "base": """# Examples

## Basic Usage

```python
def process_data(data):
    result = []
    for item in data:
        result.append(item.upper())
    return result
```

## Advanced Usage

See advanced.md for more details.
""",
    "local": """# Examples

## Basic Usage

```python
def process_data(data):
    # Optimized version using list comprehension
    return [item.upper() for item in data]
```

## Advanced Usage

See advanced.md for more details.
""",
    "remote": """# Examples

## Basic Usage

```python
def process_data(data):
    result = []
    for item in data:
        # Add validation
        if item:
            result.append(item.upper())
    return result
```

## Advanced Usage

See advanced.md for more details.
"""
}

# Scenario 7: List modifications (auto-mergeable)
CONFLICT_SCENARIO_7 = {
    "base": """# Changelog

## Version 1.0

- Initial release
- Basic features

## Version 0.9

- Beta release
""",
    "local": """# Changelog

## Version 1.1

- Bug fixes
- Performance improvements

## Version 1.0

- Initial release
- Basic features

## Version 0.9

- Beta release
""",
    "remote": """# Changelog

## Version 1.0

- Initial release
- Basic features
- Documentation updates

## Version 0.9

- Beta release
"""
}

# Scenario 8: Missing base (new page, conflicting initial content)
CONFLICT_SCENARIO_8 = {
    "base": None,  # No base version
    "local": """# New Feature

## Implementation

Implemented using approach A.

## Testing

Unit tests included.
""",
    "remote": """# New Feature

## Implementation

Implemented using approach B.

## Testing

Integration tests included.
"""
}

# Scenario 9: Heading structure changes (conflicting)
CONFLICT_SCENARIO_9 = {
    "base": """# Project Guide

## Getting Started

Installation instructions.

## Usage

Usage examples.

## FAQ

Common questions.
""",
    "local": """# Project Guide

## Quick Start

### Installation

Installation instructions.

### First Steps

Getting started guide.

## Usage

Usage examples.

## FAQ

Common questions.
""",
    "remote": """# Project Guide

## Getting Started

Installation instructions.

### Prerequisites

System requirements.

## Usage

Usage examples.

## Troubleshooting

Common issues.

## FAQ

Common questions.
"""
}

# Scenario 10: Large content blocks (conflicting)
CONFLICT_SCENARIO_10 = {
    "base": """# Tutorial

## Introduction

This tutorial covers basic concepts.

## Step 1

First, set up your environment.

## Step 2

Next, configure your settings.

## Conclusion

You've completed the tutorial.
""",
    "local": """# Tutorial

## Introduction

This comprehensive tutorial covers basic and advanced concepts.

## Prerequisites

Before starting, ensure you have:
- Python 3.8+
- Git installed
- Text editor

## Step 1

First, set up your development environment with all dependencies.

## Step 2

Next, configure your settings using the provided template.

## Step 3

Deploy your first application.

## Conclusion

You've completed the tutorial and built your first app.
""",
    "remote": """# Tutorial

## Introduction

This tutorial covers basic concepts with practical examples.

## Step 1

First, set up your environment following our quickstart guide.

## Step 2

Next, configure your settings in the config file.

## Step 3

Test your installation.

## Troubleshooting

Common issues and solutions.

## Conclusion

You've completed the tutorial.
"""
}

# Helper constant for test metadata
CONFLICT_SCENARIOS = {
    "scenario_1": {
        "name": "Overlapping Installation Changes",
        "expected_conflict": True,
        "conflict_section": "Installation",
        "data": CONFLICT_SCENARIO_1
    },
    "scenario_2": {
        "name": "Non-Overlapping Section Changes",
        "expected_conflict": False,
        "auto_mergeable": True,
        "data": CONFLICT_SCENARIO_2
    },
    "scenario_3": {
        "name": "Identical Changes",
        "expected_conflict": False,
        "auto_mergeable": True,
        "data": CONFLICT_SCENARIO_3
    },
    "scenario_4": {
        "name": "Multi-Section Conflicts",
        "expected_conflict": True,
        "conflict_sections": ["Authentication", "Endpoints", "Rate Limiting"],
        "data": CONFLICT_SCENARIO_4
    },
    "scenario_5": {
        "name": "Table Structure Conflicts",
        "expected_conflict": True,
        "conflict_section": "User Table",
        "data": CONFLICT_SCENARIO_5
    },
    "scenario_6": {
        "name": "Code Block Conflicts",
        "expected_conflict": True,
        "conflict_section": "Basic Usage",
        "data": CONFLICT_SCENARIO_6
    },
    "scenario_7": {
        "name": "List Additions (Auto-Merge)",
        "expected_conflict": False,
        "auto_mergeable": True,
        "data": CONFLICT_SCENARIO_7
    },
    "scenario_8": {
        "name": "Missing Base Version",
        "expected_conflict": True,
        "has_base": False,
        "data": CONFLICT_SCENARIO_8
    },
    "scenario_9": {
        "name": "Heading Structure Changes",
        "expected_conflict": True,
        "conflict_sections": ["Getting Started", "Structure"],
        "data": CONFLICT_SCENARIO_9
    },
    "scenario_10": {
        "name": "Large Content Blocks",
        "expected_conflict": True,
        "conflict_sections": ["Introduction", "Step 1", "Step 2", "Step 3"],
        "data": CONFLICT_SCENARIO_10
    }
}
