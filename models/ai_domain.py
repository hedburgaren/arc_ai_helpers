# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging
from urllib.parse import quote as url_quote

_logger = logging.getLogger(__name__)

def _get_nocodb_url(env):
    return env['ir.config_parameter'].sudo().get_param(
        'arc_ai_helpers.nocodb_url', 'https://nocodb.hedburgaren.se')

def _get_nocodb_table(env):
    return env['ir.config_parameter'].sudo().get_param(
        'arc_ai_helpers.nocodb_table', 'migavxhndqhdb6k')


class ArcAiDomain(models.Model):
    _name = 'arc.ai.domain'
    _description = 'AI Domain / Tenant'
    _order = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # === Basic Info ===
    name = fields.Char(
        string='Domain Name',
        required=True,
        tracking=True,
        help='Lowercase identifier, e.g. plastshop, arcgruppen'
    )
    display_name = fields.Char(
        string='Display Name',
        tracking=True,
        help='Human-readable name, e.g. PlastShop AB'
    )
    domain_type = fields.Selection([
        ('odoo', 'Odoo'),
        ('wordpress', 'WordPress'),
        ('external', 'External'),
    ], string='Type', default='odoo', tracking=True)
    url = fields.Char(string='Website URL')
    active = fields.Boolean(default=True, tracking=True)

    # === Brand Profile ===
    brand_tagline = fields.Char(
        string='Tagline',
        help='Short slogan, e.g. "Din partner för teknisk plast"'
    )
    brand_description = fields.Text(
        string='Brand Description',
        help='2-3 sentences about what the company does'
    )
    brand_colors = fields.Char(
        string='Brand Colors',
        help='Hex codes, e.g. "#0066CC (primary), #FF6600 (accent)"'
    )
    target_audience = fields.Text(
        string='Target Audience',
        help='Who are the customers? Industries, company size, roles'
    )
    tone_of_voice = fields.Char(
        string='Tone of Voice',
        help='e.g. "Professional, technically competent, solution-oriented"'
    )
    industry = fields.Char(string='Industry')
    key_products = fields.Text(string='Key Products/Services')
    competitors = fields.Char(string='Competitors')
    unique_selling_points = fields.Text(string='Unique Selling Points')
    content_guidelines = fields.Text(
        string='Content Guidelines',
        help='Rules for AI-generated content'
    )
    forbidden_words = fields.Char(
        string='Forbidden Words',
        help='Comma-separated words the AI should never use'
    )

    # === Operations ===
    slack_channel_id = fields.Char(string='Slack Channel ID')
    qdrant_collection = fields.Char(
        string='Qdrant Collection',
        compute='_compute_qdrant_collection',
        store=True
    )
    workers = fields.Char(
        string='Active Workers',
        help='Comma-separated: content, code, sales, research, odoo, hseq, elearning'
    )
    voice_prompt = fields.Text(string='Voice Prompt (TTS)')

    # === Billing ===
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        tracking=True,
        help='Customer to invoice for AI usage'
    )
    product_id = fields.Many2one(
        'product.product',
        string='AI Service Product',
        help='Product used for invoicing'
    )
    billing_rate = fields.Float(
        string='Rate (SEK/1k tokens)',
        digits=(10, 2),
        help='Price per 1000 tokens in SEK'
    )
    billing_email = fields.Char(string='Billing Email')
    
    # === Usage Tracking ===
    token_count = fields.Integer(
        string='Total Tokens',
        readonly=True,
        help='Total tokens used since creation'
    )
    token_limit = fields.Integer(
        string='Token Limit',
        help='Maximum tokens allowed (0 = unlimited)'
    )
    monthly_token_usage = fields.Integer(
        string='Monthly Usage',
        readonly=True,
        help='Tokens used this month'
    )
    last_invoice_date = fields.Date(string='Last Invoice Date', readonly=True)
    estimated_monthly_cost = fields.Float(
        string='Est. Monthly Cost (SEK)',
        compute='_compute_estimated_cost',
        store=True
    )

    # === NocoDB Sync ===
    nocodb_id = fields.Integer(string='NocoDB ID', readonly=True)
    last_sync = fields.Datetime(string='Last Sync', readonly=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Domain name must be unique!'),
    ]

    @api.depends('name')
    def _compute_qdrant_collection(self):
        for rec in self:
            rec.qdrant_collection = f"{rec.name}_memory" if rec.name else False

    @api.depends('monthly_token_usage', 'billing_rate')
    def _compute_estimated_cost(self):
        for rec in self:
            if rec.monthly_token_usage and rec.billing_rate:
                rec.estimated_monthly_cost = (rec.monthly_token_usage / 1000) * rec.billing_rate
            else:
                rec.estimated_monthly_cost = 0.0

    def action_sync_from_nocodb(self):
        """Pull latest data from NocoDB"""
        self.ensure_one()
        api_key = self.env['ir.config_parameter'].sudo().get_param('arc_ai.nocodb_api_key')
        if not api_key:
            raise UserError("NocoDB API key not configured. Set arc_ai.nocodb_api_key in System Parameters.")
        
        try:
            resp = requests.get(
                f"{_get_nocodb_url(self.env)}/api/v2/tables/{_get_nocodb_table(self.env)}/records",
                params={'where': f'(Name,eq,{url_quote(self.name)})'},
                headers={'xc-token': api_key},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get('list'):
                raise UserError(f"Domain '{self.name}' not found in NocoDB")
            
            d = data['list'][0]
            self.write({
                'nocodb_id': d.get('Id'),
                'display_name': d.get('Display Name'),
                'domain_type': d.get('Type', 'odoo'),
                'url': d.get('URL'),
                'brand_tagline': d.get('Brand Tagline'),
                'brand_description': d.get('Brand Description'),
                'brand_colors': d.get('Brand Colors'),
                'target_audience': d.get('Target Audience'),
                'tone_of_voice': d.get('Tone of Voice'),
                'industry': d.get('Industry'),
                'key_products': d.get('Key Products/Services'),
                'competitors': d.get('Competitors'),
                'unique_selling_points': d.get('Unique Selling Points'),
                'content_guidelines': d.get('Content Guidelines'),
                'forbidden_words': d.get('Forbidden Words'),
                'slack_channel_id': d.get('Slack Channel ID'),
                'workers': d.get('Workers'),
                'billing_rate': (d.get('Billing Rate SEK/1k tokens') or 0) / 100,  # öre -> SEK
                'token_count': d.get('Token Count') or 0,
                'token_limit': d.get('Token Limit') or 0,
                'monthly_token_usage': d.get('Monthly Token Usage') or 0,
                'active': d.get('Active', True),
                'last_sync': fields.Datetime.now(),
            })
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Sync Complete', 'message': f'Synced {self.name} from NocoDB',
                               'type': 'success', 'sticky': False}}
        except requests.RequestException as e:
            raise UserError(f"Failed to sync from NocoDB: {e}")

    def action_sync_to_nocodb(self):
        """Push changes to NocoDB"""
        self.ensure_one()
        api_key = self.env['ir.config_parameter'].sudo().get_param('arc_ai.nocodb_api_key')
        if not api_key:
            raise UserError("NocoDB API key not configured.")
        
        if not self.nocodb_id:
            raise UserError("No NocoDB ID. Sync from NocoDB first or create via Domain Manager.")
        
        try:
            payload = {
                'Id': self.nocodb_id,
                'display_name': self.display_name,
                'type': self.domain_type,
                'url': self.url,
                'brand_tagline': self.brand_tagline,
                'brand_description': self.brand_description,
                'brand_colors': self.brand_colors,
                'target_audience': self.target_audience,
                'tone_of_voice': self.tone_of_voice,
                'industry': self.industry,
                'key_products': self.key_products,
                'competitors': self.competitors,
                'unique_selling_points': self.unique_selling_points,
                'content_guidelines': self.content_guidelines,
                'forbidden_words': self.forbidden_words,
                'slack_channel_id': self.slack_channel_id,
                'workers': self.workers,
                'billing_rate': int((self.billing_rate or 0) * 100),  # SEK -> öre
                'token_limit': self.token_limit,
                'active': self.active,
            }
            
            resp = requests.patch(
                f"{_get_nocodb_url(self.env)}/api/v2/tables/{_get_nocodb_table(self.env)}/records",
                json=payload,
                headers={'xc-token': api_key, 'Content-Type': 'application/json'},
                timeout=10
            )
            resp.raise_for_status()
            self.last_sync = fields.Datetime.now()
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Sync Complete', 'message': f'Pushed {self.name} to NocoDB',
                               'type': 'success', 'sticky': False}}
        except requests.RequestException as e:
            raise UserError(f"Failed to sync to NocoDB: {e}")

    def action_refresh_usage(self):
        """Refresh token usage from NocoDB"""
        self.ensure_one()
        api_key = self.env['ir.config_parameter'].sudo().get_param('arc_ai.nocodb_api_key')
        if not api_key:
            raise UserError("NocoDB API key not configured.")
        
        try:
            resp = requests.get(
                f"{_get_nocodb_url(self.env)}/api/v2/tables/{_get_nocodb_table(self.env)}/records",
                params={'where': f'(Name,eq,{url_quote(self.name)})'},
                headers={'xc-token': api_key},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data.get('list'):
                d = data['list'][0]
                self.write({
                    'token_count': d.get('Token Count') or 0,
                    'monthly_token_usage': d.get('Monthly Token Usage') or 0,
                    'last_sync': fields.Datetime.now(),
                })
            
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Usage Updated', 
                               'message': f'{self.name}: {self.monthly_token_usage:,} tokens this month',
                               'type': 'info', 'sticky': False}}
        except requests.RequestException as e:
            raise UserError(f"Failed to refresh usage: {e}")

    def action_create_invoice(self):
        """Create invoice for monthly usage"""
        self.ensure_one()
        if not self.partner_id:
            raise UserError("No customer assigned to this domain.")
        if not self.product_id:
            raise UserError("No AI service product configured.")
        if self.monthly_token_usage <= 0:
            raise UserError("No usage to invoice.")
        if self.billing_rate <= 0:
            raise UserError("Billing rate is zero.")
        
        amount = (self.monthly_token_usage / 1000) * self.billing_rate
        
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'name': f"AI-tjänster {self.display_name or self.name} - {self.monthly_token_usage:,} tokens",
                'quantity': self.monthly_token_usage / 1000,
                'price_unit': self.billing_rate,
            })],
        })
        
        self.write({
            'last_invoice_date': fields.Date.today(),
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def cron_sync_all_from_nocodb(self):
        """Scheduled action to sync all domains from NocoDB"""
        api_key = self.env['ir.config_parameter'].sudo().get_param('arc_ai.nocodb_api_key')
        if not api_key:
            _logger.warning("NocoDB API key not configured, skipping sync")
            return
        
        try:
            resp = requests.get(
                f"{_get_nocodb_url(self.env)}/api/v2/tables/{_get_nocodb_table(self.env)}/records",
                headers={'xc-token': api_key},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            
            for d in data.get('list', []):
                domain_name = d.get('Name')
                if not domain_name:
                    continue
                
                existing = self.search([('name', '=', domain_name)], limit=1)
                vals = {
                    'name': domain_name,
                    'nocodb_id': d.get('Id'),
                    'display_name': d.get('Display Name'),
                    'domain_type': d.get('Type', 'odoo'),
                    'url': d.get('URL'),
                    'brand_tagline': d.get('Brand Tagline'),
                    'token_count': d.get('Token Count') or 0,
                    'monthly_token_usage': d.get('Monthly Token Usage') or 0,
                    'billing_rate': (d.get('Billing Rate SEK/1k tokens') or 0) / 100,
                    'active': d.get('Active', True),
                    'last_sync': fields.Datetime.now(),
                }
                
                if existing:
                    existing.write(vals)
                else:
                    self.create(vals)
            
            _logger.info(f"Synced {len(data.get('list', []))} domains from NocoDB")
        except Exception as e:
            _logger.error(f"Failed to sync domains from NocoDB: {e}")

    @api.model
    def cron_monthly_invoicing(self):
        """Scheduled action to create invoices for all billable domains"""
        domains = self.search([
            ('active', '=', True),
            ('partner_id', '!=', False),
            ('product_id', '!=', False),
            ('billing_rate', '>', 0),
            ('monthly_token_usage', '>', 0),
        ])
        
        invoices_created = 0
        for domain in domains:
            try:
                domain.action_refresh_usage()
                if domain.monthly_token_usage > 0:
                    domain.action_create_invoice()
                    invoices_created += 1
            except Exception as e:
                _logger.error(f"Failed to invoice domain {domain.name}: {e}")
        
        _logger.info(f"Monthly invoicing complete: {invoices_created} invoices created")
        
        # Reset monthly usage in NocoDB
        try:
            n8n_url = self.env['ir.config_parameter'].sudo().get_param(
                'arc_ai_helpers.n8n_webhook_url', 'https://n8n.hedburgaren.se')
            n8n_api_key = self.env['ir.config_parameter'].sudo().get_param(
                'arc_ai_helpers.n8n_api_key', '')
            requests.post(
                f"{n8n_url}/webhook/domain-manager",
                json={'action': 'reset_monthly'},
                headers={'Authorization': f'Bearer {n8n_api_key}'} if n8n_api_key else {},
                timeout=30
            )
        except Exception as e:
            _logger.error(f"Failed to reset monthly usage: {e}")
