# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    # =========================================================
    # PERMISOS Y AUTORIZACIONES DEL VEHÍCULO
    # =========================================================
    permit_ids = fields.One2many(
        'fleet.vehicle.permit', 'vehicle_id',
        string='Permisos y Autorizaciones',
    )
    active_permit_count = fields.Integer(
        compute='_compute_permit_counts', string='Permisos Vigentes',
    )
    expiring_permit_count = fields.Integer(
        compute='_compute_permit_counts', string='Permisos por Vencer',
    )

    # =========================================================
    # CAPACIDADES PARA TRANSPORTE DE RESIDUOS
    # =========================================================
    waste_transport_type = fields.Selection([
        ('rp', 'Residuos Peligrosos'),
        ('rme', 'Residuos de Manejo Especial'),
        ('rsu', 'Residuos Sólidos Urbanos'),
        ('mixto', 'Mixto (RP + RME + RSU)'),
    ], string='Tipo de Residuos Autorizado')

    max_weight_kg = fields.Float(string='Capacidad Máx. Peso (Kg)')
    max_volume_m3 = fields.Float(string='Capacidad Máx. Volumen (m³)')
    vehicle_unit_type = fields.Selection([
        ('camion', 'Camión'),
        ('camioneta', 'Camioneta'),
        ('trailer', 'Tráiler'),
        ('pipa', 'Pipa'),
        ('volteo', 'Volteo'),
        ('plataforma', 'Plataforma'),
        ('otro', 'Otro'),
    ], string='Tipo de Unidad')

    remolque_placa_1 = fields.Char(string='Placa Remolque 1')
    remolque_placa_2 = fields.Char(string='Placa Remolque 2')

    # =========================================================
    # DISPONIBILIDAD
    # =========================================================
    planning_slot_ids = fields.One2many(
        'service.planning.slot', 'vehicle_id',
        string='Asignaciones de Servicio',
    )
    is_available = fields.Boolean(
        compute='_compute_is_available',
        string='Disponible Hoy',
        store=False,
    )

    # =========================================================
    # SEMARNAT / SCT
    # =========================================================
    sct_permit_number = fields.Char(string='No. Permiso SCT')
    semarnat_authorization = fields.Char(string='Autorización SEMARNAT')
    insurance_policy = fields.Char(string='No. Póliza Seguro Ambiental')
    insurance_expiry = fields.Date(string='Vencimiento Seguro Ambiental')

    @api.depends('permit_ids', 'permit_ids.state', 'permit_ids.expiry_date')
    def _compute_permit_counts(self):
        today = fields.Date.today()
        soon = today + timedelta(days=30)
        for vehicle in self:
            permits = vehicle.permit_ids
            vehicle.active_permit_count = len(permits.filtered(lambda p: p.state == 'active'))
            vehicle.expiring_permit_count = len(permits.filtered(
                lambda p: p.state == 'active' and p.expiry_date and p.expiry_date <= soon
            ))

    def _compute_is_available(self):
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0)
        today_end = today_start + timedelta(days=1)
        for vehicle in self:
            busy_slots = self.env['service.planning.slot'].search_count([
                ('vehicle_id', '=', vehicle.id),
                ('date_planned', '<', today_end),
                ('date_end', '>', today_start),
                ('state', 'not in', ['cancel', 'done']),
            ])
            vehicle.is_available = busy_slots == 0

    # =========================================================
    # AUTO-MARCAR is_driver AL ASIGNAR CONDUCTOR EN FLOTA
    # =========================================================
    @api.onchange('driver_id')
    def _onchange_driver_id_mark_is_driver(self):
        """Cuando se asigna un conductor en flota, marcarlo como is_driver."""
        if self.driver_id and hasattr(self.driver_id, 'is_driver') and not self.driver_id.is_driver:
            self.driver_id.sudo().write({'is_driver': True})

    def write(self, vals):
        res = super().write(vals)
        if 'driver_id' in vals and vals['driver_id']:
            driver = self.env['res.partner'].browse(vals['driver_id'])
            if driver.exists() and hasattr(driver, 'is_driver') and not driver.is_driver:
                driver.sudo().write({'is_driver': True})
        return res


class FleetVehiclePermit(models.Model):
    _name = 'fleet.vehicle.permit'
    _description = 'Permiso/Autorización de Vehículo'
    _order = 'expiry_date asc'
    _inherit = ['mail.thread']

    vehicle_id = fields.Many2one('fleet.vehicle', required=True, ondelete='cascade', string='Vehículo')
    name = fields.Char(string='Nombre del Permiso', required=True)
    permit_type = fields.Selection([
        ('sct', 'Permiso SCT'),
        ('semarnat', 'Autorización SEMARNAT'),
        ('seguro_ambiental', 'Seguro Ambiental'),
        ('seguro_carga', 'Seguro de Carga'),
        ('verificacion', 'Verificación Vehicular'),
        ('licencia_federal', 'Licencia Federal (Unidad)'),
        ('otro', 'Otro'),
    ], string='Tipo', required=True)
    number = fields.Char(string='Número de Documento')
    issue_date = fields.Date(string='Fecha de Emisión')
    expiry_date = fields.Date(string='Fecha de Vencimiento', tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Vigente'),
        ('expired', 'Vencido'),
        ('renewed', 'Renovado'),
    ], default='draft', tracking=True, string='Estado')
    attachment_ids = fields.Many2many('ir.attachment', string='Documentos Adjuntos')
    notes = fields.Text(string='Notas')

    issuing_authority = fields.Char(string='Autoridad Emisora')
    holder_type = fields.Selection([
        ('vehicle', 'Vehículo'),
        ('company', 'Empresa Transportista'),
        ('client', 'Cliente (Generador)'),
    ], default='vehicle', string='Titular')

    @api.model
    def _cron_check_permit_expiry(self):
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'active'),
            ('expiry_date', '<', today),
        ])
        expired.write({'state': 'expired'})

        soon = today + timedelta(days=30)
        expiring = self.search([
            ('state', '=', 'active'),
            ('expiry_date', '>=', today),
            ('expiry_date', '<=', soon),
        ])
        for permit in expiring:
            permit.vehicle_id.message_post(
                body=_('⚠️ El permiso "%s" (%s) vence el %s.') % (
                    permit.name, permit.number or '', permit.expiry_date
                ),
                subject=_('Permiso próximo a vencer'),
                message_type='notification',
            )