# -*- coding: utf-8 -*-
"""
AI Assistant model - Virtual employees with AI capabilities.

Each assistant has:
- Name and email (like a real employee)
- Specialization (content, sales, HSEQ, etc.)
- Email integration
- Slack integration
- n8n workflow binding
"""
import logging
import json
import uuid
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AiAssistant(models.Model):
    """AI Assistant - A virtual employee with AI capabilities."""
    _name = 'ai.assistant'
    _description = 'AI Assistant'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    # Identity
    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
        help="The assistant's name (e.g., 'Alex', 'Sam')"
    )
    email = fields.Char(
        string='Email',
        required=True,
        tracking=True,
        help="Email address for this assistant (e.g., alex@plastshop.se)"
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    
    # Avatar/Image
    image_128 = fields.Image(string='Avatar', max_width=128, max_height=128)
    
    # Specialization
    specialization = fields.Selection([
        ('general', 'General Assistant'),
        ('content', 'Content Creator'),
        ('sales', 'Sales Assistant'),
        ('support', 'Customer Support'),
        ('hseq', 'HSEQ Compliance'),
        ('research', 'Research Assistant'),
        ('code', 'Code Assistant'),
        ('elearning', 'eLearning Creator'),
    ], string='Specialization', default='general', required=True, tracking=True)
    
    description = fields.Text(
        string='Description',
        help="Description of this assistant's role and capabilities"
    )
    
    # Personality/Persona
    persona_prompt = fields.Text(
        string='Persona Prompt',
        help="System prompt that defines the assistant's personality and behavior"
    )
    language = fields.Selection([
        ('sv', 'Swedish'),
        ('en', 'English'),
        ('fi', 'Finnish'),
        ('nb', 'Norwegian'),
        ('da', 'Danish'),
        ('de', 'German'),
        ('es', 'Spanish'),
        ('auto', 'Auto-detect'),
    ], string='Primary Language', default='sv')
    
    # Integration settings
    slack_user_id = fields.Char(
        string='Slack User ID',
        help="Slack user ID for this assistant (if integrated)"
    )
    slack_channel_ids = fields.Char(
        string='Slack Channels',
        help="Comma-separated list of Slack channel IDs this assistant monitors"
    )
    n8n_workflow_id = fields.Char(
        string='n8n Workflow ID',
        help="ID of the n8n workflow that handles this assistant's tasks"
    )
    n8n_webhook_url = fields.Char(
        string='n8n Webhook URL',
        help="Webhook URL to trigger the assistant's workflow"
    )
    
    # AI Provider settings (can override global settings)
    ai_provider = fields.Selection([
        ('default', 'Use Default'),
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic Claude'),
        ('ollama', 'Ollama (Self-hosted)'),
    ], string='AI Provider', default='default')
    ai_model = fields.Char(
        string='AI Model',
        help="Specific model to use (e.g., gpt-4, claude-3-opus)"
    )
    temperature = fields.Float(
        string='Temperature',
        default=0.7,
        help="Creativity level (0.0-1.0)"
    )
    
    # Memory/Context
    qdrant_collection = fields.Char(
        string='Qdrant Collection',
        help="Qdrant collection name for this assistant's memory"
    )
    context_window = fields.Integer(
        string='Context Window',
        default=10,
        help="Number of previous messages to include in context"
    )
    
    # Statistics
    task_count = fields.Integer(
        string='Task Count',
        compute='_compute_task_count'
    )
    message_count_ai = fields.Integer(
        string='Messages Handled',
        compute='_compute_message_count'
    )
    last_activity = fields.Datetime(
        string='Last Activity',
        readonly=True
    )
    
    # Company (for multi-tenant isolation)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help="Company this assistant belongs to (tenant isolation)"
    )
    
    _sql_constraints = [
        ('email_company_uniq', 'unique(email, company_id)',
         'Email must be unique per company!'),
        ('name_company_uniq', 'unique(name, company_id)',
         'Assistant name must be unique per company!'),
    ]
    
    @api.depends('company_id')
    def _compute_task_count(self):
        for assistant in self:
            assistant.task_count = self.env['ai.task'].search_count([
                ('assistant_id', '=', assistant.id)
            ])
    
    @api.depends('company_id')
    def _compute_message_count(self):
        for assistant in self:
            assistant.message_count_ai = self.env['ai.log'].search_count([
                ('assistant_id', '=', assistant.id)
            ])
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Auto-generate Qdrant collection name if not provided
            if not vals.get('qdrant_collection'):
                company = self.env['res.company'].browse(
                    vals.get('company_id', self.env.company.id)
                )
                safe_name = (vals.get('name', 'assistant') or 'assistant').lower()
                safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)
                company_slug = ''.join(c if c.isalnum() else '_' for c in company.name.lower())
                vals['qdrant_collection'] = f"{company_slug}_{safe_name}_memory"
        
        return super().create(vals_list)
    
    def action_view_tasks(self):
        """View tasks assigned to this assistant."""
        self.ensure_one()
        return {
            'name': _('Tasks for %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ai.task',
            'view_mode': 'list,form',
            'domain': [('assistant_id', '=', self.id)],
            'context': {'default_assistant_id': self.id},
        }
    
    def action_view_logs(self):
        """View interaction logs for this assistant."""
        self.ensure_one()
        return {
            'name': _('Logs for %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ai.log',
            'view_mode': 'list,form',
            'domain': [('assistant_id', '=', self.id)],
        }
    
    def action_send_test_message(self):
        """Send a test message to this assistant."""
        self.ensure_one()
        return {
            'name': _('Test %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ai.task',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_assistant_id': self.id,
                'default_task_type': 'chat',
                'default_input_text': _('Hello %s, this is a test message.') % self.name,
            },
        }
    
    def trigger_n8n_workflow(self, payload):
        """
        Trigger the n8n workflow for this assistant.
        
        Args:
            payload: dict with task data to send to n8n
            
        Returns:
            Response from n8n webhook
        """
        self.ensure_one()
        
        if not self.n8n_webhook_url:
            raise UserError(_("No n8n webhook URL configured for %s") % self.name)
        
        import requests
        
        # Add assistant context to payload
        payload.update({
            'assistant_id': self.id,
            'assistant_name': self.name,
            'assistant_email': self.email,
            'specialization': self.specialization,
            'company_id': self.company_id.id,
            'company_name': self.company_id.name,
            'persona_prompt': self.persona_prompt or '',
            'language': self.language,
            'qdrant_collection': self.qdrant_collection,
        })
        
        try:
            response = requests.post(
                self.n8n_webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            
            # Update last activity
            self.last_activity = fields.Datetime.now()
            
            return response.json() if response.text else {}
            
        except requests.exceptions.RequestException as e:
            _logger.error("Failed to trigger n8n workflow for %s: %s", self.name, str(e))
            raise UserError(_("Failed to trigger workflow: %s") % str(e))
    
    def process_incoming_email(self, message_dict):
        """
        Process an incoming email for this assistant.
        
        Args:
            message_dict: dict with email data (from, subject, body, etc.)
            
        Returns:
            ai.task record
        """
        self.ensure_one()
        
        task = self.env['ai.task'].create({
            'assistant_id': self.id,
            'task_type': 'email',
            'source': 'email',
            'input_text': message_dict.get('body', ''),
            'metadata': json.dumps({
                'from': message_dict.get('from'),
                'subject': message_dict.get('subject'),
                'message_id': message_dict.get('message_id'),
                'in_reply_to': message_dict.get('in_reply_to'),
            }),
            'state': 'pending',
        })
        
        # Trigger n8n workflow if configured
        if self.n8n_webhook_url:
            try:
                self.trigger_n8n_workflow({
                    'task_id': task.id,
                    'task_type': 'email',
                    'input': message_dict,
                })
                task.state = 'processing'
            except Exception as e:
                task.write({
                    'state': 'failed',
                    'error_message': str(e),
                })
        
        return task
    
    def process_slack_message(self, slack_event):
        """
        Process an incoming Slack message for this assistant.
        
        Args:
            slack_event: dict with Slack event data
            
        Returns:
            ai.task record
        """
        self.ensure_one()
        
        task = self.env['ai.task'].create({
            'assistant_id': self.id,
            'task_type': 'chat',
            'source': 'slack',
            'input_text': slack_event.get('text', ''),
            'metadata': json.dumps({
                'channel': slack_event.get('channel'),
                'user': slack_event.get('user'),
                'ts': slack_event.get('ts'),
                'thread_ts': slack_event.get('thread_ts'),
            }),
            'state': 'pending',
        })
        
        # Trigger n8n workflow if configured
        if self.n8n_webhook_url:
            try:
                self.trigger_n8n_workflow({
                    'task_id': task.id,
                    'task_type': 'slack',
                    'input': slack_event,
                })
                task.state = 'processing'
            except Exception as e:
                task.write({
                    'state': 'failed',
                    'error_message': str(e),
                })
        
        return task
