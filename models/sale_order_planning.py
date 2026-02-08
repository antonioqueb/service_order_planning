# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # =========================================================
    # RELACIÓN CON PLANEACIÓN
    # =========================================================
    planning_slot_ids = fields.One2many(
        'service.planning.slot', 'sale_order_id',
        string='Programación de Servicios',
    )
    planning_slot_count = fields.Integer(
        compute='_compute_planning_counts',
        string='Servicios Programados',
    )
    planning_pending_count = fields.Integer(
        compute='_compute_planning_counts',
        string='Pendientes de OS',
    )

    @api.depends('planning_slot_ids', 'planning_slot_ids.state', 'planning_slot_ids.service_order_id')
    def _compute_planning_counts(self):
        for order in self:
            slots = order.planning_slot_ids
            order.planning_slot_count = len(slots)
            order.planning_pending_count = len(slots.filtered(
                lambda s: s.state in ('draft', 'scheduled') and not s.service_order_id
            ))

    # =========================================================
    # ACCIONES
    # =========================================================
    def action_view_planning_slots(self):
        self.ensure_one()
        return {
            'name': _('Programación de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'service.planning.slot',
            'view_mode': 'calendar,list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def action_schedule_services(self):
        self.ensure_one()
        return {
            'name': _('Programar Servicios para %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'service.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_pickup_location_id': self.pickup_location_id.id if self.pickup_location_id else False,
                'default_destination_id': self.final_destination_id.id if self.final_destination_id else False,
                'default_service_frequency': self.service_frequency if hasattr(self, 'service_frequency') else False,
            },
        }

    def action_create_pending_service_orders(self):
        self.ensure_one()
        pending = self.planning_slot_ids.filtered(
            lambda s: s.state in ('draft', 'scheduled') and not s.service_order_id
        )
        if not pending:
            raise UserError(_('No hay servicios programados pendientes de crear orden.'))
        return pending.action_mass_create_service_orders()