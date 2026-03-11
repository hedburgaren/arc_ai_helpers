# ARC AI Helpers

AI-powered assistants for Odoo 18 with email, Slack, and n8n integration.

## Overview

ARC AI Helpers provides virtual AI employees that can:
- **Receive and respond to emails** (like a real employee)
- **Respond in Slack** channels and DMs
- **Execute tasks** via n8n workflows
- **Learn over time** with persistent memory (Qdrant)
- **Maintain strict tenant isolation** (no data cross-contamination)

## Features

### AI Assistants
Each assistant has:
- Name and email address (e.g., "Alex" at alex@plastshop.se)
- Specialization (content, sales, support, HSEQ, etc.)
- Persona/personality configuration
- Integration with Slack and n8n

### Multi-Provider Support
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude 3)
- Azure OpenAI
- Ollama (self-hosted)
- Custom endpoints

### Task Queue
- Async task processing via n8n
- Confidence classification (high/medium/low)
- Feedback loop (approve/edit/reject)
- Automatic retry on failure

### Privacy & Security
- PII redaction before AI calls
- API keys stored securely (not in Notion!)
- Multi-company isolation
- Audit logging

## Installation

```bash
# Clone to your Odoo addons directory
git clone https://github.com/hedburgaren/arc_ai_helpers.git

# Install in Odoo
# Apps > Update Apps List > Search "AI Helpers" > Install
```

## Configuration

1. **AI Settings**: Configure your AI provider (OpenAI, Anthropic, etc.)
2. **n8n Integration**: Set webhook URLs for task processing
3. **Qdrant**: Configure vector database for memory
4. **Create Assistants**: Add AI assistants with names and emails

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/ai/task/create` | POST | Create a new task |
| `/api/ai/task/callback` | POST | n8n callback for results |
| `/api/ai/task/<id>` | GET | Get task status |
| `/api/ai/assistant/<id>/message` | POST | Send message to assistant |
| `/api/ai/webhook/email` | POST | Incoming email webhook |
| `/api/ai/webhook/slack` | POST | Slack event webhook |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Odoo (arc_ai_helpers)                    │
│  - AI Assistants (name, email, persona)                     │
│  - Task Queue                                               │
│  - Audit Logs                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    n8n Workflows                            │
│  - Task processing                                          │
│  - AI API calls                                             │
│  - Email/Slack responses                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Qdrant (Memory)                          │
│  - Persistent conversation context                          │
│  - Per-tenant collections                                   │
└─────────────────────────────────────────────────────────────┘
```

## Dependencies

- Odoo 18
- `mail` module
- `contacts` module

## License

LGPL-3

## Author

ARC Gruppen AB - https://arcgruppen.se
ARC AI Helpers - Odoo module for AI-powered assistants with email, Slack, and n8n integration
