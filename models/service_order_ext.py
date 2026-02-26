# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ServiceOrder(models.Model):
    _inherit = 'service.order'

    # =========================================================
    # RELACIÓN CON PLANEACIÓN
    # =========================================================
    planning_slot_ids = fields.One2many(
        'service.planning.slot', 'service_order_id',
        string='Programación',
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
    )
    vehicle_license_plate = fields.Char(
        related='fleet_vehicle_id.license_plate',
        string='Placa Vehículo (Flota)', store=True,
    )

    @api.depends('planning_slot_ids')
    def _compute_planning_slot_count(self):
        for order in self:
            order.planning_slot_count = len(order.planning_slot_ids)

    # =========================================================
    # ACCIONES
    # =========================================================
    def action_view_planning_slots(self):
        """Ver calendario completo de la cotización de esta OS."""
        self.ensure_one()
        domain = ['|',
            ('service_order_id', '=', self.id),
            ('sale_order_id', '=', self.sale_order_id.id),
        ] if self.sale_order_id else [('service_order_id', '=', self.id)]

        return {
            'name': _('Calendario de Servicios'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.planning.slot',
            'view_mode': 'calendar,list,form',
            'domain': domain,
            'context': {
                'default_sale_order_id': self.sale_order_id.id if self.sale_order_id else False,
            },
        }

    @api.onchange('fleet_vehicle_id')
    def _onchange_fleet_vehicle(self):
        """Propagar datos del vehículo de flota a los campos existentes."""
        if not self.fleet_vehicle_id:
            return
        
        v = self.fleet_vehicle_id
        
        # Siempre sobreescribir con datos del vehículo seleccionado
        self.camion = v.display_name
        self.numero_placa = v.license_plate or ''
        
        if hasattr(v, 'remolque_placa_1'):
            self.remolque1 = v.remolque_placa_1 or ''
            self.remolque2 = v.remolque_placa_2 or ''
        
        # Auto-asignar chofer del vehículo
        if v.driver_id:
            self.chofer_id = v.driver_id

    @api.onchange('chofer_id')
    def _onchange_chofer_id_driver_check(self):
        """Marcar automáticamente como is_driver si se asigna como chofer."""
        if self.chofer_id and not self.chofer_id.is_driver:
            # En onchange solo actualizamos el valor en memoria para mostrar advertencia
            # El write real se hace en el override de create/write
            return {
                'warning': {
                    'title': _('Chofer no marcado'),
                    'message': _(
                        'El contacto "%s" no está marcado como Chofer. '
                        'Se marcará automáticamente al guardar.'
                    ) % self.chofer_id.name,
                }
            }