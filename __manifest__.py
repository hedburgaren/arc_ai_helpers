# -*- coding: utf-8 -*-
{
    'name': 'ARC AI Helpers',
    'version': '18.0.1.0.0',
    'category': 'Productivity/AI',
    'summary': 'AI-powered assistants with email, Slack, and n8n integration',
    'description': """
ARC AI Helpers
==============

AI-powered assistants that act as virtual employees with:
- Name and email address (like a real employee)
- Email integration (receive and respond to emails)
- Slack integration (respond in channels and DMs)
- n8n workflow integration
- Multi-tenant support with strict data isolation
- Persistent memory via Qdrant
- Confidence classification and feedback loops

Key Features
------------
* AI Assistants with human-like identity
* Multi-provider support (OpenAI, Anthropic, Ollama, etc.)
* Prompt template management with versioning
* Audit logging for compliance
* Privacy and PII redaction
* Workflow automation
* Context management with customer history integration

Architecture
------------
This module is the Odoo bridge to the AI system running in n8n.
Data stays isolated per tenant (company) - no cross-contamination.
    """,
    'author': 'ARC Gruppen AB',
    'website': 'https://arcgruppen.se',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'account',
        'product',
    ],
    'data': [
        # Security
        'security/ai_helpers_security.xml',
        'security/ir.model.access.csv',
        # Data
        'data/ai_assistant_data.xml',
        'data/ai_domain_data.xml',
        # Views
        'views/ai_assistant_views.xml',
        'views/ai_settings_views.xml',
        'views/ai_task_views.xml',
        'views/ai_log_views.xml',
        'views/ai_prompt_template_views.xml',
        'views/ai_domain_views.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {},
    'images': ['static/description/banner.png'],
}
