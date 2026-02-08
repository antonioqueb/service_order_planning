# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import timedelta


class ServiceCompanyPermit(models.Model):
    _name = 'service.company.permit'
    _description = 'Permiso/Autorización de la Empresa'
    _order = 'expiry_date asc'
    _inherit = ['mail.thread']

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Empresa/Transportista',
        help='Puede ser nuestra empresa o un transportista externo.',
    )
    name = fields.Char(string='Nombre del Permiso', required=True)
    permit_type = fields.Selection([
        ('semarnat_recoleccion', 'Autorización SEMARNAT Recolección'),
        ('semarnat_transporte', 'Autorización SEMARNAT Transporte'),
        ('semarnat_acopio', 'Autorización SEMARNAT Acopio'),
        ('semarnat_tratamiento', 'Autorización SEMARNAT Tratamiento'),
        ('sct_autotransporte', 'Permiso SCT Autotransporte'),
        ('licencia_ambiental', 'Licencia Ambiental Estatal'),
        ('seguro_ambiental', 'Seguro de Responsabilidad Ambiental'),
        ('registro_generador', 'Registro como Generador (NRA)'),
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
    attachment_ids = fields.Many2many('ir.attachment', string='Documentos')
    notes = fields.Text(string='Notas')
    scope = fields.Selection([
        ('national', 'Nacional'),
        ('state', 'Estatal'),
        ('municipal', 'Municipal'),
    ], string='Alcance')


class ServiceClientAuthorization(models.Model):
    _name = 'service.client.authorization'
    _description = 'Autorización del Cliente'
    _order = 'expiry_date asc'
    _inherit = ['mail.thread']

    partner_id = fields.Many2one(
        'res.partner', string='Cliente (Generador)', required=True,
    )
    name = fields.Char(string='Nombre de la Autorización', required=True)
    authorization_type = fields.Selection([
        ('nra', 'Número de Registro Ambiental (NRA)'),
        ('coa', 'Cédula de Operación Anual (COA)'),
        ('licencia_ambiental', 'Licencia Ambiental'),
        ('plan_manejo', 'Plan de Manejo de Residuos'),
        ('autorizacion_descarga', 'Autorización de Descarga'),
        ('bitacora', 'Bitácora de Residuos'),
        ('otro', 'Otro'),
    ], string='Tipo', required=True)
    number = fields.Char(string='Número de Documento')
    issue_date = fields.Date(string='Fecha de Emisión')
    expiry_date = fields.Date(string='Fecha de Vencimiento', tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Vigente'),
        ('expired', 'Vencido'),
    ], default='draft', tracking=True, string='Estado')
    attachment_ids = fields.Many2many('ir.attachment', string='Documentos')
    notes = fields.Text(string='Notas')
