# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

# Mapa de frecuencias a días
FREQUENCY_DAYS = {
    'diaria': 1,
    '2_veces_semana': 3,  # ~cada 3.5 días
    '3_veces_semana': 2,  # ~cada 2.3 días
    'semanal': 7,
    'quincenal': 15,
    'mensual': 30,
    'bimensual': 60,
    'trimestral': 90,
    'semestral': 180,
    'anual': 365,
}


class ServicePlanningSlot(models.Model):
    _name = 'service.planning.slot'
    _description = 'Slot de Planeación de Servicio'
    _order = 'date_start asc, priority desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        compute='_compute_name', store=True, readonly=False,
    )

    # =========================================================
    # RELACIONES PRINCIPALES
    # =========================================================
    service_order_id = fields.Many2one(
        'service.order', string='Orden de Servicio',
        ondelete='set null', tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, tracking=True,
    )
    sale_order_id = fields.Many2one(
        related='service_order_id.sale_order_id',
        string='Cotización', store=True,
    )

    # =========================================================
    # PROGRAMACIÓN
    # =========================================================
    date_start = fields.Datetime(
        string='Fecha/Hora Inicio', required=True, tracking=True,
    )
    date_end = fields.Datetime(
        string='Fecha/Hora Fin', required=True, tracking=True,
    )
    date_deadline = fields.Date(
        string='Fecha Límite',
        help='Fecha máxima para completar el servicio.',
    )
    all_day = fields.Boolean(string='Todo el Día', default=False)
    duration = fields.Float(
        string='Duración (hrs)', compute='_compute_duration', store=True,
    )

    # =========================================================
    # ASIGNACIÓN DE RECURSOS
    # =========================================================
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehículo', tracking=True,
    )
    driver_id = fields.Many2one(
        'res.partner', string='Chofer', tracking=True,
        domain="[('is_driver', '=', True)]",
    )
    user_id = fields.Many2one(
        'res.users', string='Responsable',
        default=lambda self: self.env.user,
        tracking=True,
    )
    team_member_ids = fields.Many2many(
        'res.partner', 'planning_slot_team_rel',
        'slot_id', 'partner_id',
        string='Equipo de Trabajo',
    )

    # =========================================================
    # UBICACIÓN
    # =========================================================
    pickup_location_id = fields.Many2one(
        'res.partner', string='Ubicación de Recolección',
    )
    destination_id = fields.Many2one(
        'res.partner', string='Destino Final',
    )

    # =========================================================
    # ESTADO Y PRIORIDAD
    # =========================================================
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('scheduled', 'Programado'),
        ('in_progress', 'En Proceso'),
        ('done', 'Completado'),
        ('cancel', 'Cancelado'),
        ('rescheduled', 'Reprogramado'),
    ], default='draft', tracking=True, string='Estado')

    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Baja'),
        ('2', 'Media'),
        ('3', 'Alta'),
        ('4', 'Urgente'),
    ], default='0', string='Prioridad', tracking=True)

    # =========================================================
    # COLOR PARA CALENDARIO
    # =========================================================
    color = fields.Integer(
        string='Color', compute='_compute_color', store=True,
    )

    # =========================================================
    # FRECUENCIA Y RECURRENCIA
    # =========================================================
    is_recurring = fields.Boolean(string='Servicio Recurrente')
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
    parent_slot_id = fields.Many2one(
        'service.planning.slot', string='Slot Padre (Recurrencia)',
        ondelete='set null',
    )
    child_slot_ids = fields.One2many(
        'service.planning.slot', 'parent_slot_id',
        string='Slots Generados',
    )

    # =========================================================
    # NOTAS Y SEGUIMIENTO
    # =========================================================
    notes = fields.Text(string='Notas de Planeación')
    completion_notes = fields.Text(string='Notas de Cierre')

    # =========================================================
    # RESIDUOS ESPERADOS
    # =========================================================
    waste_type = fields.Selection([
        ('rp', 'Residuos Peligrosos'),
        ('rme', 'Residuos de Manejo Especial'),
        ('rsu', 'Residuos Sólidos Urbanos'),
        ('mixto', 'Mixto'),
    ], string='Tipo de Residuo')
    estimated_weight_kg = fields.Float(string='Peso Estimado (Kg)')
    estimated_volume_m3 = fields.Float(string='Volumen Estimado (m³)')

    # =========================================================
    # COMPUTES
    # =========================================================
    @api.depends('service_order_id', 'partner_id', 'date_start')
    def _compute_name(self):
        for slot in self:
            parts = []
            if slot.service_order_id:
                parts.append(slot.service_order_id.name)
            if slot.partner_id:
                parts.append(slot.partner_id.name or '')
            if slot.date_start:
                parts.append(slot.date_start.strftime('%d/%m/%Y'))
            slot.name = ' - '.join(parts) if parts else _('Nuevo Slot')

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for slot in self:
            if slot.date_start and slot.date_end:
                delta = slot.date_end - slot.date_start
                slot.duration = delta.total_seconds() / 3600.0
            else:
                slot.duration = 0.0

    @api.depends('state', 'priority')
    def _compute_color(self):
        """
        Color mapping para calendario:
        0=gris, 1=rojo, 2=naranja, 3=amarillo, 4=azul claro,
        5=morado, 6=rosa, 7=azul, 8=cyan, 9=verde, 10=verde oscuro
        """
        state_colors = {
            'draft': 0,       # Gris
            'scheduled': 4,   # Azul claro
            'in_progress': 3, # Amarillo
            'done': 10,       # Verde oscuro
            'cancel': 1,      # Rojo
            'rescheduled': 2, # Naranja
        }
        priority_override = {
            '4': 1,  # Urgente = Rojo
            '3': 2,  # Alta = Naranja
        }
        for slot in self:
            if slot.priority in priority_override and slot.state not in ('done', 'cancel'):
                slot.color = priority_override[slot.priority]
            else:
                slot.color = state_colors.get(slot.state, 0)

    # =========================================================
    # CONSTRAINS
    # =========================================================
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for slot in self:
            if slot.date_start and slot.date_end and slot.date_end < slot.date_start:
                raise ValidationError(_('La fecha de fin no puede ser anterior a la fecha de inicio.'))

    @api.constrains('vehicle_id', 'date_start', 'date_end')
    def _check_vehicle_overlap(self):
        """Validar que el vehículo no tenga overlap de horarios."""
        for slot in self:
            if not slot.vehicle_id or not slot.date_start or not slot.date_end:
                continue
            overlapping = self.search([
                ('id', '!=', slot.id),
                ('vehicle_id', '=', slot.vehicle_id.id),
                ('state', 'not in', ['cancel', 'done']),
                ('date_start', '<', slot.date_end),
                ('date_end', '>', slot.date_start),
            ])
            if overlapping:
                raise ValidationError(
                    _('El vehículo %s ya tiene un servicio programado en ese horario:\n%s') % (
                        slot.vehicle_id.display_name,
                        '\n'.join(overlapping.mapped('name'))
                    )
                )

    @api.constrains('driver_id', 'date_start', 'date_end')
    def _check_driver_overlap(self):
        """Validar que el chofer no tenga overlap."""
        for slot in self:
            if not slot.driver_id or not slot.date_start or not slot.date_end:
                continue
            overlapping = self.search([
                ('id', '!=', slot.id),
                ('driver_id', '=', slot.driver_id.id),
                ('state', 'not in', ['cancel', 'done']),
                ('date_start', '<', slot.date_end),
                ('date_end', '>', slot.date_start),
            ])
            if overlapping:
                raise ValidationError(
                    _('El chofer %s ya tiene un servicio programado en ese horario:\n%s') % (
                        slot.driver_id.display_name,
                        '\n'.join(overlapping.mapped('name'))
                    )
                )

    # =========================================================
    # ONCHANGES
    # =========================================================
    @api.onchange('service_order_id')
    def _onchange_service_order(self):
        if self.service_order_id:
            so = self.service_order_id
            self.partner_id = so.partner_id
            self.pickup_location_id = so.pickup_location_id
            self.destination_id = so.destinatario_id
            self.driver_id = so.chofer_id
            self.waste_type = self._get_predominant_waste_type(so)
            self.estimated_weight_kg = so.total_weight_kg
            if so.service_frequency:
                self.service_frequency = so.service_frequency
                self.is_recurring = so.service_frequency not in ('una_sola_vez', 'bajo_demanda', 'emergencia', 'unico', 'irregular', 'estacional')

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start and not self.date_end:
            self.date_end = self.date_start + timedelta(hours=2)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Auto-propagar datos del vehículo."""
        if self.vehicle_id:
            # Si el vehículo tiene driver asignado en fleet
            if self.vehicle_id.driver_id and not self.driver_id:
                driver = self.vehicle_id.driver_id
                if driver.is_driver:
                    self.driver_id = driver

    # =========================================================
    # HELPERS
    # =========================================================
    def _get_predominant_waste_type(self, service_order):
        types = set()
        for line in service_order.line_ids:
            if line.residue_type:
                types.add(line.residue_type)
        if not types:
            return False
        if len(types) > 1:
            return 'mixto'
        return types.pop()

    # =========================================================
    # ACTIONS
    # =========================================================
    def action_schedule(self):
        for slot in self:
            if not slot.vehicle_id or not slot.driver_id:
                raise UserError(_('Debe asignar vehículo y chofer para programar el servicio.'))
            slot.state = 'scheduled'

    def action_start(self):
        self.write({'state': 'in_progress'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reschedule(self):
        """Marca como reprogramado y abre wizard para nueva fecha."""
        self.ensure_one()
        return {
            'name': _('Reprogramar Servicio'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_slot_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_vehicle_id': self.vehicle_id.id if self.vehicle_id else False,
                'default_driver_id': self.driver_id.id if self.driver_id else False,
            },
        }

    def action_reset_draft(self):
        self.filtered(lambda s: s.state in ('cancel', 'rescheduled')).write({'state': 'draft'})

    def action_create_service_order(self):
        """Crea una orden de servicio desde el slot si no existe."""
        self.ensure_one()
        if self.service_order_id:
            raise UserError(_('Este slot ya tiene una Orden de Servicio vinculada.'))

        vals = {
            'partner_id': self.partner_id.id,
            'date_order': self.date_start,
            'pickup_location_id': self.pickup_location_id.id if self.pickup_location_id else False,
            'destinatario_id': self.destination_id.id if self.destination_id else False,
            'chofer_id': self.driver_id.id if self.driver_id else False,
            'service_frequency': self.service_frequency,
        }

        # Propagar datos del vehículo
        if self.vehicle_id:
            vals.update({
                'camion': self.vehicle_id.display_name,
                'numero_placa': self.vehicle_id.license_plate,
                'remolque1': self.vehicle_id.remolque_placa_1 or '',
                'remolque2': self.vehicle_id.remolque_placa_2 or '',
            })

        service = self.env['service.order'].create(vals)
        self.service_order_id = service.id

        return {
            'name': _('Orden de Servicio'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.order',
            'view_mode': 'form',
            'res_id': service.id,
            'target': 'current',
        }

    def action_generate_recurring_slots(self):
        """Genera slots futuros basados en la frecuencia."""
        self.ensure_one()
        if not self.is_recurring or not self.service_frequency:
            raise UserError(_('Este slot no tiene frecuencia de recurrencia configurada.'))

        if not self.recurrence_end_date:
            raise UserError(_('Debe definir la fecha "Repetir Hasta" para generar slots recurrentes.'))

        days_interval = FREQUENCY_DAYS.get(self.service_frequency)
        if not days_interval:
            raise UserError(_('Frecuencia no soportada para generación automática.'))

        created = self.env['service.planning.slot']
        current_start = self.date_start + timedelta(days=days_interval)
        duration_delta = self.date_end - self.date_start

        while current_start.date() <= self.recurrence_end_date:
            new_slot = self.copy({
                'date_start': current_start,
                'date_end': current_start + duration_delta,
                'parent_slot_id': self.id,
                'state': 'draft',
                'is_recurring': False,
                'child_slot_ids': False,
            })
            created |= new_slot
            current_start += timedelta(days=days_interval)

        if created:
            return {
                'name': _('Slots Generados (%d)') % len(created),
                'type': 'ir.actions.act_window',
                'res_model': 'service.planning.slot',
                'view_mode': 'list,calendar,form',
                'domain': [('id', 'in', created.ids)],
            }
        else:
            raise UserError(_('No se generaron slots. Verifique las fechas.'))

    def action_view_service_order(self):
        self.ensure_one()
        if not self.service_order_id:
            raise UserError(_('No hay orden de servicio vinculada.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'service.order',
            'view_mode': 'form',
            'res_id': self.service_order_id.id,
            'target': 'current',
        }
