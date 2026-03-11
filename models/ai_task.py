# -*- coding: utf-8 -*-
"""
AI Task - Task queue for AI assistants.
"""
import logging
import json
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiTask(models.Model):
    """Task queue for AI assistants."""
    _name = 'ai.task'
    _description = 'AI Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )
    assistant_id = fields.Many2one(
        'ai.assistant',
        string='Assistant',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    
    # Task type and source
    task_type = fields.Selection([
        ('chat', 'Chat/Conversation'),
        ('email', 'Email Response'),
        ('content', 'Content Generation'),
        ('analysis', 'Data Analysis'),
        ('translation', 'Translation'),
        ('summary', 'Summarization'),
        ('code', 'Code Generation'),
        ('custom', 'Custom Task'),
    ], string='Task Type', required=True, default='chat', tracking=True)
    
    source = fields.Selection([
        ('manual', 'Manual'),
        ('email', 'Email'),
        ('slack', 'Slack'),
        ('api', 'API'),
        ('webhook', 'Webhook'),
        ('scheduled', 'Scheduled'),
    ], string='Source', default='manual', tracking=True)
    
    # Input/Output
    input_text = fields.Text(string='Input', required=True)
    output_text = fields.Text(string='Output', readonly=True)
    
    # Metadata (JSON)
    metadata = fields.Text(
        string='Metadata',
        help="JSON-encoded metadata (e.g., email headers, Slack context)"
    )
    
    # State
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='pending', required=True, tracking=True)
    
    # Confidence and feedback
    confidence = fields.Selection([
        ('high', 'High (Auto-approve)'),
        ('medium', 'Medium (Review suggested)'),
        ('low', 'Low (Manual review required)'),
    ], string='Confidence', readonly=True)
    confidence_score = fields.Float(
        string='Confidence Score',
        readonly=True,
        help="Numeric confidence score (0.0-1.0)"
    )
    
    feedback = fields.Selection([
        ('approved', 'Approved'),
        ('edited', 'Edited'),
        ('rejected', 'Rejected'),
    ], string='Feedback', tracking=True)
    feedback_notes = fields.Text(string='Feedback Notes')
    
    # Error handling
    error_message = fields.Text(string='Error Message', readonly=True)
    retry_count = fields.Integer(string='Retry Count', default=0, readonly=True)
    max_retries = fields.Integer(string='Max Retries', default=3)
    
    # Timing
    started_at = fields.Datetime(string='Started At', readonly=True)
    completed_at = fields.Datetime(string='Completed At', readonly=True)
    duration_seconds = fields.Integer(
        string='Duration (s)',
        compute='_compute_duration',
        store=True
    )
    
    # Related records
    res_model = fields.Char(string='Related Model')
    res_id = fields.Integer(string='Related Record ID')
    res_name = fields.Char(string='Related Record', compute='_compute_res_name')
    
    # Company (tenant isolation)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    @api.depends('started_at', 'completed_at')
    def _compute_duration(self):
        for task in self:
            if task.started_at and task.completed_at:
                delta = task.completed_at - task.started_at
                task.duration_seconds = int(delta.total_seconds())
            else:
                task.duration_seconds = 0
    
    @api.depends('res_model', 'res_id')
    def _compute_res_name(self):
        for task in self:
            if task.res_model and task.res_id:
                try:
                    record = self.env[task.res_model].browse(task.res_id)
                    task.res_name = record.display_name if record.exists() else ''
                except Exception:
                    task.res_name = ''
            else:
                task.res_name = ''
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('ai.task') or _('New')
        return super().create(vals_list)
    
    def action_process(self):
        """Process this task."""
        self.ensure_one()
        
        if self.state != 'pending':
            raise UserError(_("Only pending tasks can be processed."))
        
        self.write({
            'state': 'processing',
            'started_at': fields.Datetime.now(),
        })
        
        # Trigger n8n workflow
        if self.assistant_id.n8n_webhook_url:
            try:
                metadata = json.loads(self.metadata or '{}')
                result = self.assistant_id.trigger_n8n_workflow({
                    'task_id': self.id,
                    'task_type': self.task_type,
                    'input': self.input_text,
                    'metadata': metadata,
                    'res_model': self.res_model,
                    'res_id': self.res_id,
                })
                
                # If n8n returns immediate result
                if result.get('output'):
                    self.write({
                        'state': 'completed',
                        'output_text': result.get('output'),
                        'confidence': result.get('confidence', 'medium'),
                        'confidence_score': result.get('confidence_score', 0.5),
                        'completed_at': fields.Datetime.now(),
                    })
                    
            except Exception as e:
                self._handle_error(str(e))
        else:
            self._handle_error(_("No n8n webhook configured for assistant"))
        
        return True
    
    def action_retry(self):
        """Retry a failed task."""
        self.ensure_one()
        
        if self.state != 'failed':
            raise UserError(_("Only failed tasks can be retried."))
        
        if self.retry_count >= self.max_retries:
            raise UserError(_("Maximum retry count reached."))
        
        self.write({
            'state': 'pending',
            'retry_count': self.retry_count + 1,
            'error_message': False,
        })
        
        return self.action_process()
    
    def action_cancel(self):
        """Cancel this task."""
        self.ensure_one()
        
        if self.state in ('completed', 'cancelled'):
            raise UserError(_("Cannot cancel completed or already cancelled tasks."))
        
        self.state = 'cancelled'
        return True
    
    def action_approve(self):
        """Approve the task output."""
        self.ensure_one()
        self.feedback = 'approved'
        return True
    
    def action_reject(self):
        """Reject the task output."""
        self.ensure_one()
        self.feedback = 'rejected'
        return True
    
    def _handle_error(self, error_message):
        """Handle task error."""
        self.ensure_one()
        
        _logger.error("AI Task %s failed: %s", self.name, error_message)
        
        self.write({
            'state': 'failed',
            'error_message': error_message,
            'completed_at': fields.Datetime.now(),
        })
    
    def receive_n8n_result(self, result):
        """
        Receive result from n8n webhook callback.
        
        Args:
            result: dict with output, confidence, etc.
        """
        self.ensure_one()
        
        if result.get('error'):
            self._handle_error(result.get('error'))
            return False
        
        self.write({
            'state': 'completed',
            'output_text': result.get('output', ''),
            'confidence': result.get('confidence', 'medium'),
            'confidence_score': result.get('confidence_score', 0.5),
            'completed_at': fields.Datetime.now(),
        })
        
        return True
    
    @api.model
    def cleanup_old_tasks(self, days=30):
        """Cron job to cleanup old completed/cancelled tasks."""
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old_tasks = self.search([
            ('state', 'in', ['completed', 'cancelled']),
            ('create_date', '<', cutoff),
        ])
        
        count = len(old_tasks)
        old_tasks.unlink()
        
        _logger.info("Cleaned up %d old AI tasks", count)
        return count
