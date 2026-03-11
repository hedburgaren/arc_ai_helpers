# -*- coding: utf-8 -*-
"""
AI Mixin - Add AI capabilities to any model.
"""
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AiMixin(models.AbstractModel):
    """
    Mixin for AI-powered features.
    Inherit this in any model to add AI capabilities.
    """
    _name = 'ai.mixin'
    _description = 'AI Mixin'

    ai_processed = fields.Boolean(
        string='AI Processed',
        default=False,
        help="Indicates if this record has been processed by AI"
    )
    ai_last_update = fields.Datetime(
        string='Last AI Update',
        readonly=True
    )
    ai_notes = fields.Text(
        string='AI Notes',
        help="Notes from AI processing"
    )
    ai_confidence = fields.Float(
        string='AI Confidence',
        readonly=True,
        help="Confidence score from last AI operation (0.0-1.0)"
    )

    def action_process_with_ai(self):
        """
        Process this record with AI.
        Override in specific models for custom behavior.
        """
        self.ensure_one()
        
        prompt = self._get_ai_prompt()
        context = self._get_ai_context()
        
        result = self._call_ai_service(prompt, context)
        
        self.write({
            'ai_processed': True,
            'ai_last_update': fields.Datetime.now(),
            'ai_notes': result.get('response', ''),
            'ai_confidence': result.get('confidence', 0.0),
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Processing'),
                'message': _('AI processing completed.'),
                'type': 'success',
            }
        }

    def _get_ai_prompt(self):
        """
        Get the AI prompt for this record.
        Override in specific models.
        """
        return f"Analyze record {self.id} of model {self._name}"

    def _get_ai_context(self):
        """
        Get context for AI processing.
        Override in specific models.
        """
        return {
            'model': self._name,
            'record_id': self.id,
            'company': self.env.company.name,
        }

    def _call_ai_service(self, prompt, context=None):
        """
        Call AI service with prompt and context.
        
        Args:
            prompt: The prompt to send
            context: Optional context dict
            
        Returns:
            dict with 'response' and 'confidence'
        """
        # Get default assistant or settings
        settings = self.env['ai.settings'].get_active_settings()
        
        if settings.provider == 'mock':
            return {
                'success': True,
                'response': f'Mock AI response for: {prompt[:100]}...',
                'confidence': 0.5,
            }
        
        # For real providers, this would make the actual API call
        # In practice, tasks go through n8n workflows
        _logger.info("AI service called for %s with prompt: %s", self._name, prompt[:100])
        
        return {
            'success': True,
            'response': 'AI processing initiated. Check task queue for results.',
            'confidence': 0.0,
        }
