# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import timedelta


class FleetDriverPermit(models.Model):
    _name = 'fleet.driver.permit'
    _description = 'Permiso/Autorización de Chofer'
    _order = 'expiry_date asc'
    _inherit = ['mail.thread']

    driver_id = fields.Many2one(
        'res.partner', string='Chofer', required=True, ondelete='cascade',
    )
    name = fields.Char(string='Nombre del Permiso', required=True)
    permit_type = fields.Selection([
        ('licencia_federal', 'Licencia Federal de Conductor'),
        ('constancia_capacitacion', 'Constancia de Capacitación (NOM-023)'),
        ('examen_medico', 'Examen Médico'),
        ('curso_materiales_peligrosos', 'Curso Materiales Peligrosos'),
        ('seguro_vida', 'Seguro de Vida'),
        ('antidoping', 'Antidoping'),
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

    @api.model
    def _cron_check_driver_permit_expiry(self):
        """Marcar permisos vencidos de choferes."""
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'active'),
            ('expiry_date', '<', today),
        ])
        expired.write({'state': 'expired'})


class ResPartnerDriverExt(models.Model):
    _inherit = 'res.partner'

    is_driver = fields.Boolean(string='Es Chofer')
    driver_permit_ids = fields.One2many(
        'fleet.driver.permit', 'driver_id',
        string='Permisos del Chofer',
    )
    driver_license_type = fields.Selection([
        ('a', 'Tipo A'),
        ('b', 'Tipo B'),
        ('c', 'Tipo C'),
        ('d', 'Tipo D'),
        ('e', 'Tipo E'),
        ('federal', 'Federal'),
    ], string='Tipo de Licencia')
    driver_license_number = fields.Char(string='No. Licencia')
    driver_license_expiry = fields.Date(string='Vencimiento Licencia')

    # Capacidades del chofer
    can_transport_rp = fields.Boolean(string='Autorizado RP')
    can_transport_rme = fields.Boolean(string='Autorizado RME')

    active_driver_permit_count = fields.Integer(
        compute='_compute_driver_permit_count',
        string='Permisos Vigentes',
    )

    @api.depends('driver_permit_ids', 'driver_permit_ids.state')
    def _compute_driver_permit_count(self):
        for partner in self:
            partner.active_driver_permit_count = len(
                partner.driver_permit_ids.filtered(lambda p: p.state == 'active')
            )
