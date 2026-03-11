# -*- coding: utf-8 -*-
"""
AI Log - Audit logging for AI interactions.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiLog(models.Model):
    """Audit log for AI interactions."""
    _name = 'ai.log'
    _description = 'AI Interaction Log'
    _order = 'create_date desc'

    assistant_id = fields.Many2one(
        'ai.assistant',
        string='Assistant',
        ondelete='set null',
        index=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        index=True
    )
    task_id = fields.Many2one(
        'ai.task',
        string='Task',
        ondelete='set null',
        index=True
    )
    
    # Request/Response
    prompt = fields.Text(string='Prompt')
    response = fields.Text(string='Response')
    
    # AI details
    ai_provider = fields.Char(string='AI Provider')
    ai_model = fields.Char(string='AI Model')
    
    # Metrics
    token_count_input = fields.Integer(string='Input Tokens')
    token_count_output = fields.Integer(string='Output Tokens')
    token_count_total = fields.Integer(
        string='Total Tokens',
        compute='_compute_token_count_total',
        store=True
    )
    duration_ms = fields.Integer(string='Duration (ms)')
    
    # Status
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('timeout', 'Timeout'),
        ('rate_limited', 'Rate Limited'),
    ], string='Status', default='success')
    error_message = fields.Text(string='Error Message')
    
    # Context
    res_model = fields.Char(string='Related Model')
    res_id = fields.Integer(string='Related Record ID')
    
    # Company (tenant isolation)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    create_date = fields.Datetime(string='Date', readonly=True)
    
    @api.depends('token_count_input', 'token_count_output')
    def _compute_token_count_total(self):
        for log in self:
            log.token_count_total = (log.token_count_input or 0) + (log.token_count_output or 0)
    
    @api.model
    def log_interaction(self, assistant_id=None, prompt=None, response=None,
                       ai_provider=None, ai_model=None, token_count_input=0,
                       token_count_output=0, duration_ms=0, status='success',
                       error_message=None, task_id=None, res_model=None, res_id=None):
        """
        Log an AI interaction.
        
        Args:
            assistant_id: ID of the AI assistant
            prompt: The input prompt
            response: The AI response
            ai_provider: Provider name (openai, anthropic, etc.)
            ai_model: Model name (gpt-4, claude-3, etc.)
            token_count_input: Number of input tokens
            token_count_output: Number of output tokens
            duration_ms: Request duration in milliseconds
            status: success, error, timeout, rate_limited
            error_message: Error message if status is error
            task_id: Related ai.task ID
            res_model: Related model name
            res_id: Related record ID
            
        Returns:
            ai.log record
        """
        return self.create({
            'assistant_id': assistant_id,
            'user_id': self.env.user.id,
            'task_id': task_id,
            'prompt': prompt[:10000] if prompt else None,  # Truncate long prompts
            'response': response[:50000] if response else None,  # Truncate long responses
            'ai_provider': ai_provider,
            'ai_model': ai_model,
            'token_count_input': token_count_input,
            'token_count_output': token_count_output,
            'duration_ms': duration_ms,
            'status': status,
            'error_message': error_message,
            'res_model': res_model,
            'res_id': res_id,
        })
    
    @api.model
    def get_usage_stats(self, days=30, assistant_id=None):
        """
        Get usage statistics for the specified period.
        
        Args:
            days: Number of days to look back
            assistant_id: Optional assistant ID to filter by
            
        Returns:
            dict with usage statistics
        """
        cutoff = fields.Datetime.now() - timedelta(days=days)
        
        domain = [
            ('create_date', '>=', cutoff),
            ('company_id', '=', self.env.company.id),
        ]
        if assistant_id:
            domain.append(('assistant_id', '=', assistant_id))
        
        logs = self.search(domain)
        
        total_requests = len(logs)
        successful = len(logs.filtered(lambda l: l.status == 'success'))
        failed = len(logs.filtered(lambda l: l.status == 'error'))
        total_tokens = sum(logs.mapped('token_count_total'))
        avg_duration = sum(logs.mapped('duration_ms')) / total_requests if total_requests else 0
        
        return {
            'period_days': days,
            'total_requests': total_requests,
            'successful_requests': successful,
            'failed_requests': failed,
            'success_rate': (successful / total_requests * 100) if total_requests else 0,
            'total_tokens': total_tokens,
            'avg_duration_ms': avg_duration,
        }
    
    @api.model
    def cleanup_old_logs(self, days=90):
        """Cron job to cleanup old logs."""
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff)])
        
        count = len(old_logs)
        old_logs.unlink()
        
        _logger.info("Cleaned up %d old AI logs", count)
        return count
