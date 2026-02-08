# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ServiceOrder(models.Model):
    _inherit = 'service.order'

    # =========================================================
    # RELACIÓN CON PLANEACIÓN
    # =========================================================
    planning_slot_ids = fields.One2many(
        'service.planning.slot', 'service_order_id',
        string='Programaciones',
    )
    planning_slot_count = fields.Integer(
        compute='_compute_planning_slot_count',
        string='Programaciones',
    )

    # =========================================================
    # INTEGRACIÓN CON FLEET
    # =========================================================
    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo (Flota)',
        tracking=True,
        help='Vehículo del módulo de Flota asignado a esta orden.',
    )

    # Datos propagados del vehículo
    vehicle_license_plate = fields.Char(
        related='fleet_vehicle_id.license_plate',
        string='Placa Vehículo (Flota)',
        store=True,
    )

    @api.depends('planning_slot_ids')
    def _compute_planning_slot_count(self):
        for order in self:
            order.planning_slot_count = len(order.planning_slot_ids)

    # =========================================================
    # ACCIONES
    # =========================================================
    def action_view_planning_slots(self):
        self.ensure_one()
        return {
            'name': _('Programaciones de %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'service.planning.slot',
            'view_mode': 'calendar,list,form',
            'domain': [('service_order_id', '=', self.id)],
            'context': {
                'default_service_order_id': self.id,
                'default_partner_id': self.partner_id.id,
            },
        }

    def action_schedule_service(self):
        """Abre el wizard para programar este servicio en el calendario."""
        self.ensure_one()
        return {
            'name': _('Programar Servicio'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_service_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_driver_id': self.chofer_id.id if self.chofer_id else False,
                'default_pickup_location_id': self.pickup_location_id.id if self.pickup_location_id else False,
                'default_destination_id': self.destinatario_id.id if self.destinatario_id else False,
                'default_service_frequency': self.service_frequency,
                'default_estimated_weight_kg': self.total_weight_kg,
            },
        }

    @api.onchange('fleet_vehicle_id')
    def _onchange_fleet_vehicle(self):
        """Propagar datos del vehículo de flota a los campos existentes."""
        if self.fleet_vehicle_id:
            v = self.fleet_vehicle_id
            if not self.camion:
                self.camion = v.display_name
            if not self.numero_placa:
                self.numero_placa = v.license_plate
            if hasattr(v, 'remolque_placa_1'):
                if not self.remolque1:
                    self.remolque1 = v.remolque_placa_1
                if not self.remolque2:
                    self.remolque2 = v.remolque_placa_2
            # Auto-asignar chofer si el vehículo tiene uno
            if v.driver_id and not self.chofer_id:
                self.chofer_id = v.driver_id
