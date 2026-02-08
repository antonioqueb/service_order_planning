# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class ServiceScheduleWizard(models.TransientModel):
    _name = 'service.schedule.wizard'
    _description = 'Asistente para Programar Servicios'

    # Origen
    sale_order_id = fields.Many2one('sale.order', string='Cotización', required=True)
    slot_id = fields.Many2one('service.planning.slot', string='Slot a Reprogramar')
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id', string='Cliente', readonly=True,
    )

    # Programación
    date_start = fields.Datetime(string='Fecha/Hora Inicio', required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Fecha/Hora Fin')

    # Asignación
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    driver_id = fields.Many2one(
        'res.partner', string='Chofer',
    )
    pickup_location_id = fields.Many2one('res.partner', string='Ubicación Recolección')
    destination_id = fields.Many2one('res.partner', string='Destino Final')

    priority = fields.Selection([
        ('0', 'Normal'), ('1', 'Baja'), ('2', 'Media'),
        ('3', 'Alta'), ('4', 'Urgente'),
    ], default='0', string='Prioridad')

    # Recurrencia
    is_recurring = fields.Boolean(string='Generar Recurrencia')
    service_frequency = fields.Selection([
        ('diaria', 'Diaria'),
        ('2_veces_semana', '2 veces por semana'),
        ('3_veces_semana', '3 veces por semana'),
        ('semanal', 'Semanal'),
        ('quincenal', 'Quincenal'),
        ('mensual', 'Mensual'),
        ('bimensual', 'Bimensual'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
    ], string='Frecuencia')
    recurrence_end_date = fields.Date(string='Repetir Hasta')

    waste_type = fields.Selection([
        ('rp', 'Residuos Peligrosos'),
        ('rme', 'Residuos de Manejo Especial'),
        ('rsu', 'Residuos Sólidos Urbanos'),
        ('mixto', 'Mixto'),
    ], string='Tipo de Residuo')

    notes = fields.Text(string='Notas')
    auto_create_orders = fields.Boolean(
        string='Crear Órdenes de Servicio Inmediatamente',
        default=False,
        help='Si se marca, además de programar los slots, crea las órdenes de servicio automáticamente.',
    )

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            self.date_end = self.date_start + timedelta(hours=2)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Al seleccionar vehículo, auto-asignar conductor y marcarlo como is_driver."""
        if self.vehicle_id and self.vehicle_id.driver_id:
            driver = self.vehicle_id.driver_id
            # Marcar como is_driver si no lo está
            if hasattr(driver, 'is_driver') and not driver.is_driver:
                driver.sudo().write({'is_driver': True})
            self.driver_id = driver

    def action_confirm(self):
        self.ensure_one()

        if not self.date_end:
            self.date_end = self.date_start + timedelta(hours=2)

        if self.date_end <= self.date_start:
            raise UserError(_('La fecha de fin debe ser posterior al inicio.'))

        # Asegurar que el chofer seleccionado esté marcado como is_driver
        if self.driver_id and hasattr(self.driver_id, 'is_driver') and not self.driver_id.is_driver:
            self.driver_id.sudo().write({'is_driver': True})

        vals = {
            'sale_order_id': self.sale_order_id.id,
            'date_planned': self.date_start,
            'date_end': self.date_end,
            'vehicle_id': self.vehicle_id.id if self.vehicle_id else False,
            'driver_id': self.driver_id.id if self.driver_id else False,
            'pickup_location_id': self.pickup_location_id.id if self.pickup_location_id else False,
            'destination_id': self.destination_id.id if self.destination_id else False,
            'priority': self.priority,
            'waste_type': self.waste_type,
            'notes': self.notes,
            'is_recurring': self.is_recurring,
            'service_frequency': self.service_frequency,
            'recurrence_end_date': self.recurrence_end_date,
            'state': 'scheduled' if self.vehicle_id and self.driver_id else 'draft',
        }

        # Si es reprogramación
        if self.slot_id:
            self.slot_id.write({'state': 'rescheduled'})
            vals['parent_slot_id'] = self.slot_id.id

        new_slot = self.env['service.planning.slot'].create(vals)

        # Generar recurrencia
        all_slots = new_slot
        if self.is_recurring and self.service_frequency and self.recurrence_end_date:
            new_slot.action_generate_recurring_slots()
            all_slots = new_slot | new_slot.child_slot_ids

        # Auto-crear órdenes si se pidió
        if self.auto_create_orders:
            schedulable = all_slots.filtered(
                lambda s: not s.service_order_id and s.state in ('draft', 'scheduled')
            )
            if schedulable:
                schedulable.action_mass_create_service_orders()

        return {
            'name': _('Programación de Servicios'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.planning.slot',
            'view_mode': 'calendar,list,form',
            'domain': [('sale_order_id', '=', self.sale_order_id.id)],
            'target': 'current',
        }