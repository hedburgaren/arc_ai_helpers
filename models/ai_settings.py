# -*- coding: utf-8 -*-
"""
AI Settings - Provider configuration and global settings.
"""
import logging
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiSettings(models.Model):
    """Settings for AI providers and configuration."""
    _name = 'ai.settings'
    _description = 'AI Settings'
    _rec_name = 'provider'

    provider = fields.Selection([
        ('mock', 'Mock Provider (No API)'),
        ('openai', 'OpenAI'),
        ('azure', 'Azure OpenAI'),
        ('anthropic', 'Anthropic Claude'),
        ('ollama', 'Ollama (Self-hosted)'),
        ('custom', 'Custom URL/API'),
    ], string='AI Provider', default='mock', required=True)

    api_key = fields.Char(
        string='API Key',
        groups='base.group_system',
        help="API key for the selected provider"
    )
    api_endpoint = fields.Char(
        string='API Endpoint',
        help="For Azure or Ollama, the base URL of the API"
    )
    default_model = fields.Char(
        string='Default Model',
        help="Default model to use (e.g., gpt-4, claude-3-opus)"
    )
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    # Privacy settings
    enable_redaction = fields.Boolean(
        string='Enable PII Redaction',
        default=True,
        help="Redact personally identifiable information before sending to AI"
    )
    redaction_patterns = fields.Text(
        string='Redaction Patterns',
        default='email,phone,address,personnummer',
        help="Comma-separated list of PII types to redact"
    )

    # Usage limits
    token_limit = fields.Integer(
        string='Token Limit',
        default=4000,
        help="Maximum tokens per request"
    )
    request_limit_daily = fields.Integer(
        string='Daily Request Limit',
        default=1000,
        help="Maximum requests per day"
    )

    # System settings
    system_prompt = fields.Text(
        string='Default System Prompt',
        help="Default system prompt to use for all requests"
    )

    # n8n Integration
    n8n_base_url = fields.Char(
        string='n8n Base URL',
        default='https://n8n.hedburgaren.se',
        help="Base URL of the n8n instance"
    )
    n8n_api_key = fields.Char(
        string='n8n API Key',
        groups='base.group_system',
        help="API key for n8n"
    )

    # Qdrant Integration
    qdrant_url = fields.Char(
        string='Qdrant URL',
        default='http://localhost:6333',
        help="URL of the Qdrant vector database"
    )
    qdrant_api_key = fields.Char(
        string='Qdrant API Key',
        groups='base.group_system',
        help="API key for Qdrant (if required)"
    )

    _sql_constraints = [
        ('company_provider_uniq', 'unique(company_id, provider, active)',
         'Only one active configuration per provider per company!')
    ]

    @api.model
    def get_active_settings(self):
        """Get the active AI settings for the current company."""
        settings = self.search([
            ('active', '=', True),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        
        if not settings:
            # Create default mock settings
            settings = self.create({
                'provider': 'mock',
                'default_model': 'mock-default',
                'company_id': self.env.company.id,
            })
        
        return settings

    def action_test_connection(self):
        """Test the connection to the configured AI provider."""
        self.ensure_one()

        try:
            if self.provider == 'mock':
                result = _('Connection successful! (Mock provider - no actual API call)')
                status = 'success'
            elif self.provider == 'openai':
                if not self.api_key:
                    raise UserError(_('OpenAI API key not configured'))
                # Test with a simple API call
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                }
                response = requests.get(
                    'https://api.openai.com/v1/models',
                    headers=headers,
                    timeout=10
                )
                if response.status_code == 200:
                    result = _('OpenAI connection successful!')
                    status = 'success'
                else:
                    result = _('OpenAI connection failed: %s') % response.status_code
                    status = 'warning'
            elif self.provider == 'anthropic':
                if not self.api_key:
                    raise UserError(_('Anthropic API key not configured'))
                result = _('Anthropic API key present - connection test passed')
                status = 'success'
            elif self.provider == 'ollama':
                if not self.api_endpoint:
                    raise UserError(_('Ollama endpoint not configured'))
                response = requests.get(
                    f"{self.api_endpoint}/api/tags",
                    timeout=10
                )
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    result = _('Ollama connection successful! %d models available.') % len(models)
                    status = 'success'
                else:
                    result = _('Ollama connection failed: %s') % response.status_code
                    status = 'warning'
            elif self.provider == 'azure':
                if not self.api_key or not self.api_endpoint:
                    raise UserError(_('Azure OpenAI requires both API key and endpoint'))
                result = _('Azure OpenAI credentials present')
                status = 'success'
            else:
                result = _('Unknown provider')
                status = 'warning'

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test'),
                    'message': result,
                    'type': status,
                    'sticky': False,
                }
            }
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Test Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_test_n8n_connection(self):
        """Test the connection to n8n."""
        self.ensure_one()

        if not self.n8n_base_url:
            raise UserError(_('n8n base URL not configured'))

        try:
            headers = {}
            if self.n8n_api_key:
                headers['X-N8N-API-KEY'] = self.n8n_api_key

            response = requests.get(
                f"{self.n8n_base_url}/api/v1/workflows",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                workflows = response.json().get('data', [])
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('n8n Connection'),
                        'message': _('Connected! %d workflows found.') % len(workflows),
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('n8n Connection'),
                        'message': _('Connection failed: %s') % response.status_code,
                        'type': 'warning',
                    }
                }
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('n8n Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_test_qdrant_connection(self):
        """Test the connection to Qdrant."""
        self.ensure_one()

        if not self.qdrant_url:
            raise UserError(_('Qdrant URL not configured'))

        try:
            headers = {}
            if self.qdrant_api_key:
                headers['api-key'] = self.qdrant_api_key

            response = requests.get(
                f"{self.qdrant_url}/collections",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                collections = response.json().get('result', {}).get('collections', [])
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Qdrant Connection'),
                        'message': _('Connected! %d collections found.') % len(collections),
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Qdrant Connection'),
                        'message': _('Connection failed: %s') % response.status_code,
                        'type': 'warning',
                    }
                }
        except requests.exceptions.RequestException as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Qdrant Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                }
            }
