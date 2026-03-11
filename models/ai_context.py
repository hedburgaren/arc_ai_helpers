# -*- coding: utf-8 -*-
"""
AI Context - Conversation context management.
"""
import logging
import json
from datetime import timedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiContext(models.Model):
    """Conversation context for AI interactions."""
    _name = 'ai.context'
    _description = 'AI Context'
    _order = 'create_date desc'

    name = fields.Char(
        string='Context Name',
        compute='_compute_name',
        store=True
    )
    active = fields.Boolean(string='Active', default=True)
    
    # Context type
    context_type = fields.Selection([
        ('session', 'Session'),
        ('user', 'User'),
        ('partner', 'Partner/Customer'),
        ('case', 'Case/Ticket'),
    ], string='Context Type', required=True, default='session')
    
    # Related records
    user_id = fields.Many2one('res.users', string='User')
    partner_id = fields.Many2one('res.partner', string='Partner')
    case_id = fields.Integer(string='Case ID')  # For arc.case if installed
    session_id = fields.Char(string='Session ID')
    
    # Assistant
    assistant_id = fields.Many2one(
        'ai.assistant',
        string='Assistant',
        ondelete='cascade'
    )
    
    # Messages
    message_ids = fields.One2many(
        'ai.context.message',
        'context_id',
        string='Messages'
    )
    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count'
    )
    
    # Summary
    summary = fields.Text(
        string='Summary',
        help="AI-generated summary of the conversation"
    )
    
    # Context data (JSON)
    context_data = fields.Text(
        string='Context Data',
        help="JSON-encoded additional context"
    )
    
    # Expiration
    expire_date = fields.Date(
        string='Expire Date',
        default=lambda self: fields.Date.today() + timedelta(days=30)
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    @api.depends('context_type', 'user_id', 'partner_id', 'session_id')
    def _compute_name(self):
        for ctx in self:
            if ctx.context_type == 'user' and ctx.user_id:
                ctx.name = f"User: {ctx.user_id.name}"
            elif ctx.context_type == 'partner' and ctx.partner_id:
                ctx.name = f"Partner: {ctx.partner_id.name}"
            elif ctx.context_type == 'case' and ctx.case_id:
                ctx.name = f"Case: {ctx.case_id}"
            elif ctx.context_type == 'session' and ctx.session_id:
                ctx.name = f"Session: {ctx.session_id[:8]}..."
            else:
                ctx.name = f"Context #{ctx.id or 'New'}"
    
    @api.depends('message_ids')
    def _compute_message_count(self):
        for ctx in self:
            ctx.message_count = len(ctx.message_ids)
    
    @api.model
    def get_or_create(self, context_type, user_id=None, partner_id=None,
                     case_id=None, session_id=None, assistant_id=None):
        """
        Get existing context or create new one.
        
        Args:
            context_type: session, user, partner, or case
            user_id: res.users ID
            partner_id: res.partner ID
            case_id: arc.case ID
            session_id: Session identifier string
            assistant_id: ai.assistant ID
            
        Returns:
            ai.context record
        """
        domain = [
            ('context_type', '=', context_type),
            ('active', '=', True),
            ('company_id', '=', self.env.company.id),
        ]
        
        if context_type == 'user' and user_id:
            domain.append(('user_id', '=', user_id))
        elif context_type == 'partner' and partner_id:
            domain.append(('partner_id', '=', partner_id))
        elif context_type == 'case' and case_id:
            domain.append(('case_id', '=', case_id))
        elif context_type == 'session' and session_id:
            domain.append(('session_id', '=', session_id))
        
        if assistant_id:
            domain.append(('assistant_id', '=', assistant_id))
        
        context = self.search(domain, limit=1)
        
        if not context:
            import uuid
            context = self.create({
                'context_type': context_type,
                'user_id': user_id if context_type == 'user' else False,
                'partner_id': partner_id if context_type == 'partner' else False,
                'case_id': case_id if context_type == 'case' else False,
                'session_id': session_id or str(uuid.uuid4()),
                'assistant_id': assistant_id,
            })
        
        return context
    
    def add_message(self, role, content):
        """Add a message to this context."""
        self.ensure_one()
        return self.env['ai.context.message'].create({
            'context_id': self.id,
            'role': role,
            'content': content,
        })
    
    def get_messages(self, limit=10):
        """Get recent messages from this context."""
        self.ensure_one()
        return self.message_ids.sorted('create_date', reverse=True)[:limit].sorted('create_date')
    
    def get_messages_for_ai(self, max_messages=10):
        """
        Get messages formatted for AI API.
        
        Returns:
            List of dicts with 'role' and 'content'
        """
        self.ensure_one()
        messages = self.get_messages(limit=max_messages)
        
        result = []
        if self.summary:
            result.append({
                'role': 'system',
                'content': f"Previous conversation summary: {self.summary}"
            })
        
        for msg in messages:
            result.append({
                'role': msg.role,
                'content': msg.content,
            })
        
        return result
    
    def prune_old_messages(self, keep_count=50):
        """Prune old messages, keeping only the most recent."""
        self.ensure_one()
        
        if self.message_count <= keep_count:
            return 0
        
        messages_to_keep = self.message_ids.sorted('create_date', reverse=True)[:keep_count]
        messages_to_delete = self.message_ids - messages_to_keep
        
        count = len(messages_to_delete)
        messages_to_delete.unlink()
        
        return count
    
    @api.model
    def cleanup_expired(self):
        """Cron job to cleanup expired contexts."""
        expired = self.search([
            ('expire_date', '<', fields.Date.today()),
            ('active', '=', True),
        ])
        expired.write({'active': False})
        return len(expired)


class AiContextMessage(models.Model):
    """Individual messages within an AI context."""
    _name = 'ai.context.message'
    _description = 'AI Context Message'
    _order = 'create_date'

    context_id = fields.Many2one(
        'ai.context',
        string='Context',
        required=True,
        ondelete='cascade'
    )
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ], string='Role', required=True, default='user')
    content = fields.Text(string='Content', required=True)
    create_date = fields.Datetime(string='Created', readonly=True)
