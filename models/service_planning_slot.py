# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

FREQUENCY_DAYS = {
    'diaria': 1,
    '2_veces_semana': 3,
    '3_veces_semana': 2,
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
    _description = 'Programación de Servicio'
    _order = 'date_planned asc, priority desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        compute='_compute_name', store=True, readonly=False,
    )

    # =========================================================
    # ORIGEN: LA COTIZACIÓN (sale.order)
    # =========================================================
    sale_order_id = fields.Many2one(
        'sale.order', string='Cotización Origen',
        required=True, ondelete='cascade', tracking=True,
        help='Cotización/contrato anual de donde se programan los servicios.',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        related='sale_order_id.partner_id', store=True, readonly=True,
    )

    # =========================================================
    # RESULTADO: LA ORDEN DE SERVICIO GENERADA
    # =========================================================
    service_order_id = fields.Many2one(
        'service.order', string='Orden de Servicio',
        ondelete='set null', tracking=True, readonly=True,
        help='Orden de servicio creada a partir de esta programación.',
    )
    service_order_state = fields.Selection(
        related='service_order_id.state',
        string='Estado OS', store=True,
    )

    # =========================================================
    # PROGRAMACIÓN
    # =========================================================
    date_planned = fields.Datetime(
        string='Fecha/Hora Programada', required=True, tracking=True,
    )
    date_end = fields.Datetime(
        string='Fecha/Hora Fin Estimada', tracking=True,
    )
    date_deadline = fields.Date(string='Fecha Límite')
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
        default=lambda self: self.env.user, tracking=True,
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
        ('confirmed', 'OS Creada'),
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

    color = fields.Integer(
        string='Color', compute='_compute_color', store=True,
    )

    # =========================================================
    # RECURRENCIA
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
        'service.planning.slot', string='Slot Padre',
        ondelete='set null',
    )
    child_slot_ids = fields.One2many(
        'service.planning.slot', 'parent_slot_id',
        string='Slots Generados',
    )

    # =========================================================
    # RESIDUOS
    # =========================================================
    waste_type = fields.Selection([
        ('rp', 'Residuos Peligrosos'),
        ('rme', 'Residuos de Manejo Especial'),
        ('rsu', 'Residuos Sólidos Urbanos'),
        ('mixto', 'Mixto'),
    ], string='Tipo de Residuo')
    estimated_weight_kg = fields.Float(string='Peso Estimado (Kg)')

    notes = fields.Text(string='Notas de Planeación')

    # =========================================================
    # COMPUTES
    # =========================================================
    @api.depends('sale_order_id', 'partner_id', 'date_planned', 'service_order_id')
    def _compute_name(self):
        for slot in self:
            parts = []
            if slot.service_order_id:
                parts.append(slot.service_order_id.name)
            elif slot.sale_order_id:
                parts.append(slot.sale_order_id.name)
            if slot.partner_id:
                parts.append(slot.partner_id.name or '')
            if slot.date_planned:
                parts.append(slot.date_planned.strftime('%d/%m/%Y %H:%M'))
            slot.name = ' - '.join(parts) if parts else _('Nueva Programación')

    @api.depends('date_planned', 'date_end')
    def _compute_duration(self):
        for slot in self:
            if slot.date_planned and slot.date_end:
                delta = slot.date_end - slot.date_planned
                slot.duration = delta.total_seconds() / 3600.0
            else:
                slot.duration = 0.0

    @api.depends('state', 'priority')
    def _compute_color(self):
        state_colors = {
            'draft': 0,
            'scheduled': 4,
            'confirmed': 7,
            'done': 10,
            'cancel': 1,
            'rescheduled': 2,
        }
        priority_override = {'4': 1, '3': 2}
        for slot in self:
            if slot.priority in priority_override and slot.state not in ('done', 'cancel'):
                slot.color = priority_override[slot.priority]
            else:
                slot.color = state_colors.get(slot.state, 0)

    # =========================================================
    # CONSTRAINS
    # =========================================================
    @api.constrains('date_planned', 'date_end')
    def _check_dates(self):
        for slot in self:
            if slot.date_planned and slot.date_end and slot.date_end < slot.date_planned:
                raise ValidationError(_('La fecha de fin no puede ser anterior a la de inicio.'))

    @api.constrains('vehicle_id', 'date_planned', 'date_end')
    def _check_vehicle_overlap(self):
        for slot in self:
            if not slot.vehicle_id or not slot.date_planned or not slot.date_end:
                continue
            overlapping = self.search([
                ('id', '!=', slot.id),
                ('vehicle_id', '=', slot.vehicle_id.id),
                ('state', 'not in', ['cancel', 'done', 'rescheduled']),
                ('date_planned', '<', slot.date_end),
                ('date_end', '>', slot.date_planned),
            ])
            if overlapping:
                raise ValidationError(
                    _('El vehículo %s ya tiene servicio programado en ese horario:\n%s') % (
                        slot.vehicle_id.display_name,
                        '\n'.join(overlapping.mapped('name'))
                    ))

    @api.constrains('driver_id', 'date_planned', 'date_end')
    def _check_driver_overlap(self):
        for slot in self:
            if not slot.driver_id or not slot.date_planned or not slot.date_end:
                continue
            overlapping = self.search([
                ('id', '!=', slot.id),
                ('driver_id', '=', slot.driver_id.id),
                ('state', 'not in', ['cancel', 'done', 'rescheduled']),
                ('date_planned', '<', slot.date_end),
                ('date_end', '>', slot.date_planned),
            ])
            if overlapping:
                raise ValidationError(
                    _('El chofer %s ya tiene servicio programado en ese horario:\n%s') % (
                        slot.driver_id.display_name,
                        '\n'.join(overlapping.mapped('name'))
                    ))

    # =========================================================
    # ONCHANGES
    # =========================================================
    @api.onchange('sale_order_id')
    def _onchange_sale_order(self):
        if self.sale_order_id:
            so = self.sale_order_id
            if hasattr(so, 'pickup_location_id') and so.pickup_location_id:
                self.pickup_location_id = so.pickup_location_id
            if hasattr(so, 'final_destination_id') and so.final_destination_id:
                self.destination_id = so.final_destination_id
            if hasattr(so, 'service_frequency') and so.service_frequency:
                self.service_frequency = so.service_frequency
                self.is_recurring = so.service_frequency not in (
                    'una_sola_vez', 'bajo_demanda', 'emergencia', 'unico', 'irregular', 'estacional'
                )

    @api.onchange('date_planned')
    def _onchange_date_planned(self):
        if self.date_planned and not self.date_end:
            self.date_end = self.date_planned + timedelta(hours=2)

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id and self.vehicle_id.driver_id and not self.driver_id:
            driver = self.vehicle_id.driver_id
            if hasattr(driver, 'is_driver') and driver.is_driver:
                self.driver_id = driver

    # =========================================================
    # ACCIONES DE ESTADO
    # =========================================================
    def action_schedule(self):
        for slot in self:
            if not slot.vehicle_id or not slot.driver_id:
                raise UserError(_('Debe asignar vehículo y chofer para programar el servicio.'))
        self.write({'state': 'scheduled'})

    def action_create_service_order(self):
        """
        ACCIÓN PRINCIPAL: Crea una nueva orden de servicio independiente
        desde este slot, copiando las líneas de la cotización.
        """
        self.ensure_one()
        if self.service_order_id:
            raise UserError(_('Este slot ya tiene una Orden de Servicio creada: %s') % self.service_order_id.name)

        if self.state not in ('draft', 'scheduled'):
            raise UserError(_('Solo se pueden crear órdenes desde slots en borrador o programados.'))

        sale = self.sale_order_id
        if not sale:
            raise UserError(_('No hay cotización vinculada para crear la orden de servicio.'))

        # Construir vals para la nueva orden de servicio
        service_vals = {
            'sale_order_id': sale.id,
            'partner_id': sale.partner_id.id,
            'date_order': self.date_planned,
            'user_id': sale.user_id.id if sale.user_id else self.env.user.id,
        }

        # Campos opcionales del sale.order (de sale_crm_propagate)
        for field_name in ('service_frequency', 'residue_new', 'requiere_visita'):
            if hasattr(sale, field_name):
                service_vals[field_name] = getattr(sale, field_name)

        # Ubicaciones
        if self.pickup_location_id:
            service_vals['pickup_location_id'] = self.pickup_location_id.id
        if self.destination_id:
            service_vals['destinatario_id'] = self.destination_id.id

        # Chofer
        if self.driver_id:
            service_vals['chofer_id'] = self.driver_id.id

        # Vehículo
        if self.vehicle_id:
            service_vals['fleet_vehicle_id'] = self.vehicle_id.id
            service_vals['camion'] = self.vehicle_id.display_name
            service_vals['numero_placa'] = self.vehicle_id.license_plate or ''
            if hasattr(self.vehicle_id, 'remolque_placa_1'):
                service_vals['remolque1'] = self.vehicle_id.remolque_placa_1 or ''
                service_vals['remolque2'] = self.vehicle_id.remolque_placa_2 or ''

        # Crear la orden
        service = self.env['service.order'].create(service_vals)

        # Copiar líneas de la cotización a la orden de servicio
        for line in sale.order_line:
            is_display = line.display_type in ('line_section', 'line_note')
            has_product = bool(line.product_id)
            has_residue = bool(getattr(line, 'residue_name', False))

            if is_display or (not has_product and not has_residue):
                continue

            product_id = line.product_id.id if line.product_id else False

            # Intentar crear producto si no existe pero hay datos de residuo
            if not product_id and has_residue and hasattr(line, '_create_service_product'):
                new_product = line._create_service_product()
                if new_product:
                    product_id = new_product.id

            if not product_id:
                continue

            weight_kg = getattr(line, 'residue_weight_kg', 0.0) or 0.0
            capacity = getattr(line, 'residue_capacity', '') or ''
            uom_id = line.product_uom_id.id if hasattr(line, 'product_uom_id') and line.product_uom_id else False
            packaging_id = getattr(line, 'residue_packaging_id', False)
            packaging_id_val = packaging_id.id if packaging_id else False

            self.env['service.order.line'].create({
                'service_order_id': service.id,
                'product_id': product_id,
                'name': line.name or getattr(line, 'residue_name', '') or 'Servicio',
                'product_uom_qty': line.product_uom_qty,
                'product_uom': uom_id,
                'weight_kg': weight_kg,
                'capacity': capacity,
                'packaging_id': packaging_id_val,
                'residue_type': getattr(line, 'residue_type', False),
                'plan_manejo': getattr(line, 'plan_manejo', False),
                'price_unit': line.price_unit,
            })

        # Vincular y actualizar estado
        self.write({
            'service_order_id': service.id,
            'state': 'confirmed',
        })

        return {
            'name': _('Orden de Servicio'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.order',
            'view_mode': 'form',
            'res_id': service.id,
            'target': 'current',
        }

    def action_mass_create_service_orders(self):
        """Crea órdenes de servicio para múltiples slots seleccionados."""
        created = self.env['service.order']
        errors = []
        for slot in self:
            if slot.service_order_id:
                errors.append(_('%s ya tiene OS: %s') % (slot.name, slot.service_order_id.name))
                continue
            if slot.state not in ('draft', 'scheduled'):
                errors.append(_('%s no está en estado válido') % slot.name)
                continue
            try:
                slot.action_create_service_order()
                created |= slot.service_order_id
            except UserError as e:
                errors.append(_('%s: %s') % (slot.name, str(e)))

        if len(created) == 1:
            return {
                'name': _('Orden de Servicio'),
                'type': 'ir.actions.act_window',
                'res_model': 'service.order',
                'view_mode': 'form',
                'res_id': created.id,
                'target': 'current',
            }
        elif created:
            return {
                'name': _('Órdenes Creadas (%d)') % len(created),
                'type': 'ir.actions.act_window',
                'res_model': 'service.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created.ids)],
            }

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reschedule(self):
        self.ensure_one()
        return {
            'name': _('Reprogramar Servicio'),
            'type': 'ir.actions.act_window',
            'res_model': 'service.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_slot_id': self.id,
                'default_sale_order_id': self.sale_order_id.id,
                'default_vehicle_id': self.vehicle_id.id if self.vehicle_id else False,
                'default_driver_id': self.driver_id.id if self.driver_id else False,
            },
        }

    def action_reset_draft(self):
        self.filtered(lambda s: s.state in ('cancel', 'rescheduled')).write({'state': 'draft'})

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

    # =========================================================
    # GENERACIÓN MASIVA DE SLOTS RECURRENTES
    # =========================================================
    def action_generate_recurring_slots(self):
        self.ensure_one()
        if not self.service_frequency:
            raise UserError(_('No hay frecuencia configurada.'))
        if not self.recurrence_end_date:
            raise UserError(_('Debe definir "Repetir Hasta".'))

        days_interval = FREQUENCY_DAYS.get(self.service_frequency)
        if not days_interval:
            raise UserError(_('Frecuencia no soportada para generación automática.'))

        created = self.env['service.planning.slot']
        current_start = self.date_planned + timedelta(days=days_interval)
        duration_delta = (self.date_end - self.date_planned) if self.date_end else timedelta(hours=2)

        while current_start.date() <= self.recurrence_end_date:
            new_slot = self.copy({
                'date_planned': current_start,
                'date_end': current_start + duration_delta,
                'parent_slot_id': self.id,
                'state': 'draft',
                'is_recurring': False,
                'child_slot_ids': False,
                'service_order_id': False,
            })
            created |= new_slot
            current_start += timedelta(days=days_interval)

        if created:
            return {
                'name': _('Slots Generados (%d)') % len(created),
                'type': 'ir.actions.act_window',
                'res_model': 'service.planning.slot',
                'view_mode': 'list,calendar,form',
                'domain': [('id', 'in', (self | created).ids)],
            }
        raise UserError(_('No se generaron slots. Verifique las fechas.'))