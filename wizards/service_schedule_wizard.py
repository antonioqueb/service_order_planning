# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class ServiceScheduleWizard(models.TransientModel):
    _name = 'service.schedule.wizard'
    _description = 'Asistente para Programar Servicio'

    # Contexto
    service_order_id = fields.Many2one('service.order', string='Orden de Servicio')
    slot_id = fields.Many2one('service.planning.slot', string='Slot a Reprogramar')
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True)

    # Programación
    date_start = fields.Datetime(string='Fecha/Hora Inicio', required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Fecha/Hora Fin', required=True)
    all_day = fields.Boolean(string='Todo el Día')

    # Asignación
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehículo')
    driver_id = fields.Many2one(
        'res.partner', string='Chofer',
        domain="[('is_driver', '=', True)]",
    )
    pickup_location_id = fields.Many2one('res.partner', string='Ubicación Recolección')
    destination_id = fields.Many2one('res.partner', string='Destino Final')

    # Prioridad
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Baja'),
        ('2', 'Media'),
        ('3', 'Alta'),
        ('4', 'Urgente'),
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

    # Residuos
    waste_type = fields.Selection([
        ('rp', 'Residuos Peligrosos'),
        ('rme', 'Residuos de Manejo Especial'),
        ('rsu', 'Residuos Sólidos Urbanos'),
        ('mixto', 'Mixto'),
    ], string='Tipo de Residuo')
    estimated_weight_kg = fields.Float(string='Peso Estimado (Kg)')

    notes = fields.Text(string='Notas')

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            self.date_end = self.date_start + timedelta(hours=2)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id and self.vehicle_id.driver_id and not self.driver_id:
            if hasattr(self.vehicle_id.driver_id, 'is_driver') and self.vehicle_id.driver_id.is_driver:
                self.driver_id = self.vehicle_id.driver_id

    def action_confirm(self):
        """Crea el slot de planeación (o reprograma uno existente)."""
        self.ensure_one()

        if self.date_end <= self.date_start:
            raise UserError(_('La fecha de fin debe ser posterior al inicio.'))

        vals = {
            'partner_id': self.partner_id.id,
            'service_order_id': self.service_order_id.id if self.service_order_id else False,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'all_day': self.all_day,
            'vehicle_id': self.vehicle_id.id if self.vehicle_id else False,
            'driver_id': self.driver_id.id if self.driver_id else False,
            'pickup_location_id': self.pickup_location_id.id if self.pickup_location_id else False,
            'destination_id': self.destination_id.id if self.destination_id else False,
            'priority': self.priority,
            'waste_type': self.waste_type,
            'estimated_weight_kg': self.estimated_weight_kg,
            'notes': self.notes,
            'is_recurring': self.is_recurring,
            'service_frequency': self.service_frequency,
            'recurrence_end_date': self.recurrence_end_date,
            'state': 'scheduled' if self.vehicle_id and self.driver_id else 'draft',
        }

        if self.slot_id:
            # Reprogramar: marcar viejo como rescheduled
            self.slot_id.write({'state': 'rescheduled'})
            vals['parent_slot_id'] = self.slot_id.id
            new_slot = self.env['service.planning.slot'].create(vals)
        else:
            new_slot = self.env['service.planning.slot'].create(vals)

        # Si pidió recurrencia, generar automáticamente
        if self.is_recurring and self.service_frequency and self.recurrence_end_date:
            new_slot.action_generate_recurring_slots()

        return {
            'name': _('Programación'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.planning.slot',
            'view_mode': 'calendar,list,form',
            'domain': [('id', 'in', (new_slot | new_slot.child_slot_ids).ids)] if new_slot.child_slot_ids else [('id', '=', new_slot.id)],
            'target': 'current',
        }
