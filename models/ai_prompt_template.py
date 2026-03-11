# -*- coding: utf-8 -*-
"""
AI Prompt Template - Reusable prompt templates with versioning.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AiPromptTemplate(models.Model):
    """Reusable AI prompt templates."""
    _name = 'ai.prompt.template'
    _description = 'AI Prompt Template'
    _order = 'category, name'

    name = fields.Char(
        string='Template Name',
        required=True,
        translate=True
    )
    description = fields.Text(
        string='Description',
        translate=True
    )
    active = fields.Boolean(string='Active', default=True)
    
    # Category
    category = fields.Selection([
        ('email', 'Email'),
        ('content', 'Content'),
        ('support', 'Customer Support'),
        ('sales', 'Sales'),
        ('technical', 'Technical'),
        ('translation', 'Translation'),
        ('summary', 'Summarization'),
        ('general', 'General'),
    ], string='Category', default='general', required=True)
    
    # Template content
    system_prompt = fields.Text(
        string='System Prompt',
        help="System-level instructions for the AI"
    )
    user_prompt = fields.Text(
        string='User Prompt Template',
        required=True,
        help="Template with {placeholders} for dynamic content"
    )
    
    # Variables
    variables = fields.Text(
        string='Variables',
        help="Comma-separated list of variable names used in the template"
    )
    
    # AI Configuration
    ai_model = fields.Char(
        string='Preferred Model',
        help="Leave empty to use default"
    )
    temperature = fields.Float(
        string='Temperature',
        default=0.7,
        help="Creativity level (0.0-1.0)"
    )
    max_tokens = fields.Integer(
        string='Max Tokens',
        default=1000
    )
    
    # Versioning
    version = fields.Integer(string='Version', default=1, readonly=True)
    version_ids = fields.One2many(
        'ai.prompt.template.version',
        'template_id',
        string='Version History'
    )
    
    # Usage tracking
    usage_count = fields.Integer(string='Usage Count', readonly=True, default=0)
    last_used = fields.Datetime(string='Last Used', readonly=True)
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'Template name must be unique per company!')
    ]
    
    @api.constrains('temperature')
    def _check_temperature(self):
        for template in self:
            if template.temperature < 0 or template.temperature > 1:
                raise ValidationError(_("Temperature must be between 0.0 and 1.0"))
    
    def write(self, vals):
        """Track version changes."""
        if 'user_prompt' in vals or 'system_prompt' in vals:
            for template in self:
                # Save current version to history
                self.env['ai.prompt.template.version'].create({
                    'template_id': template.id,
                    'version': template.version,
                    'system_prompt': template.system_prompt,
                    'user_prompt': template.user_prompt,
                })
                vals['version'] = template.version + 1
        
        return super().write(vals)
    
    def render(self, variables=None):
        """
        Render the template with the given variables.
        
        Args:
            variables: dict of variable name -> value
            
        Returns:
            Rendered prompt string
        """
        self.ensure_one()
        
        prompt = self.user_prompt or ''
        
        if variables:
            for key, value in variables.items():
                prompt = prompt.replace(f'{{{key}}}', str(value))
        
        # Update usage stats
        self.write({
            'usage_count': self.usage_count + 1,
            'last_used': fields.Datetime.now(),
        })
        
        return prompt
    
    def action_view_versions(self):
        """View version history."""
        self.ensure_one()
        return {
            'name': _('Version History'),
            'type': 'ir.actions.act_window',
            'res_model': 'ai.prompt.template.version',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
        }


class AiPromptTemplateVersion(models.Model):
    """Version history for prompt templates."""
    _name = 'ai.prompt.template.version'
    _description = 'AI Prompt Template Version'
    _order = 'version desc'

    template_id = fields.Many2one(
        'ai.prompt.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    version = fields.Integer(string='Version', required=True)
    system_prompt = fields.Text(string='System Prompt')
    user_prompt = fields.Text(string='User Prompt')
    create_date = fields.Datetime(string='Created', readonly=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)
    
    def action_restore(self):
        """Restore this version."""
        self.ensure_one()
        self.template_id.write({
            'system_prompt': self.system_prompt,
            'user_prompt': self.user_prompt,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Version Restored'),
                'message': _('Version %d has been restored.') % self.version,
                'type': 'success',
            }
        }
