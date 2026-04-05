# -*- coding: utf-8 -*-
"""
Proactive event webhook controllers for AI agents.
Batch 16.2: Odoo triggers n8n on business events -> agents notify Slack.

Models from sale_management and stock only. Models from arc_industrial_ops
are in proactive_events_ops.py (loaded separately after ops is available).
"""
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

N8N_WEBHOOK_URL = 'http://n8n-hedburgaren:5678/webhook/odoo-proactive-events'
WEBHOOK_TIMEOUT = 10


def _fire_event(env, event_type, data):
    """Fire a proactive event to n8n webhook."""
    try:
        payload = {
            'event_type': event_type,
            'data': data,
            'timestamp': fields.Datetime.now().isoformat(),
        }
        requests.post(
            N8N_WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=WEBHOOK_TIMEOUT,
        )
    except Exception as e:
        _logger.warning("Proactive event %s failed: %s", event_type, e)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Override: fire event when order is confirmed."""
        res = super().action_confirm()
        for order in self:
            _fire_event(self.env, 'order_confirmed', {
                'order_id': order.id,
                'order_name': order.name,
                'partner_name': order.partner_id.name,
                'amount_total': order.amount_total,
                'currency': order.currency_id.name,
                'line_count': len(order.order_line),
                'date_order': str(order.date_order),
            })
        return res


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def write(self, vals):
        """Fire event on delayed deliveries."""
        res = super().write(vals)
        for picking in self:
            if picking.state not in ('done', 'cancel') and picking.scheduled_date:
                if picking.scheduled_date < fields.Datetime.now():
                    _fire_event(self.env, 'delivery_delayed', {
                        'picking_id': picking.id,
                        'picking_name': picking.name,
                        'partner_name': picking.partner_id.name if picking.partner_id else '',
                        'scheduled_date': str(picking.scheduled_date),
                        'origin': picking.origin or '',
                    })
        return res


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def write(self, vals):
        """Fire event when product description changes (for translation)."""
        desc_fields = {'description_sale', 'name', 'description'}
        if desc_fields & set(vals.keys()):
            for product in self:
                _fire_event(self.env, 'product_description_changed', {
                    'product_id': product.id,
                    'product_name': product.name,
                    'default_code': product.default_code or '',
                    'changed_fields': list(desc_fields & set(vals.keys())),
                })
        return super().write(vals)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _cron_check_low_stock(self):
        """Cron job: check products with low stock (< 5 units)."""
        low = self.search([
            ('location_id.usage', '=', 'internal'),
            ('quantity', '<', 5),
            ('quantity', '>=', 0),
        ])
        for quant in low:
            _fire_event(self.env, 'low_stock', {
                'product_id': quant.product_id.id,
                'product_name': quant.product_id.display_name,
                'quantity': quant.quantity,
                'location_name': quant.location_id.display_name,
            })
