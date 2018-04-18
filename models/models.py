# -*- coding: utf-8 -*-

from openerp import models, fields, api
from datetime import datetime, timedelta
from dateutil import relativedelta
from openerp.exceptions import UserError, ValidationError
import time
import numpy as np

class FinancieraCuenta(models.Model):
	_name = 'financiera.cuenta'

	_rec_name = 'display_name'
	name = fields.Char('Cuenta', readonly=True)
	display_name = fields.Char("Nombre", readonly=True)
	responsable_id = fields.Many2one('res.users', 'Responsable')
	cliente_id = fields.Many2one('res.partner', 'Cliente', required=True)
	cliente_dni = fields.Integer('Identificaicon (DNI/CUIT/CUIL)', required=True)
	limite_credito = fields.Float("Maximo monto a otorgar")
	especificacion_laboral = fields.Selection([('empleado', 'Empleado'), ('autonomo', 'Autonomo'), ('desempleado', 'Desempleado'), ('jubilado', 'Jubilado'), ('pensionado', 'Pensionado')], string='Especificacion Laboral')
	ingresos_comprobables = fields.Float("Ingresos comprobables")
	fecha_inicio_trabajo_actual = fields.Date("Fecha inicio trabajo actual")
	recibo_de_sueldo = fields.Boolean('Tiene recibo de sueldo?')
	prestamo_ids = fields.One2many("financiera.prestamo", "cuenta_id", "Prestamos")
	#prestamo_observacion_ids = fields.One2many("financiera.observacion", "prestamo_cuenta_id", "Observaciones")
	#prestamo_recibo_ids = fields.One2many("financiera.prestamo.cuota.recibo", "prestamo_cuenta_id", "Recibos")
	active = fields.Boolean("Activo", default=True)
	state = fields.Selection([('borrador', 'Borrador'), ('confirmado', 'Confirmado')], string='Estado', readonly=True, default='borrador')

	_sql_constraints=[('cliente_id_unique', 'unique(cliente_id)', 'El cliente debe tener una unica cuenta.')]
	saldo = fields.Float("Saldo", compute='_compute_saldo', readonly=True)

	@api.model
	def create(self, values):
		rec = super(FinancieraCuenta, self).create(values)
		rec.update({
			'name': 'CTA - ' + str(rec.id).zfill(6),
			'display_name': '[' + str(rec.id).zfill(6) + '] ' + str(rec.cliente_id.name),
			})
		return rec

	@api.one
	def unlink(self):
		if self.state == 'confirmado':
			raise UserError("No puede borrar una cuenta de cliente Confirmada. Puede ocultar la cuenta desactivando el campo Activo.")
		else:
			return models.Model.unlink(self)

	@api.one
	def _compute_saldo(self):
		saldo = 0
		for prestamo in self.prestamo_ids:
			saldo = saldo + prestamo.saldo
		self.saldo = saldo

	def confirmar(self, cr, uid, ids, context=None):
		self.write(cr, uid, ids, {'state':'confirmado'}, context=None)
		return True

class FinancieraPrestamo(models.Model):
	_name = 'financiera.prestamo'

	_rec_name = 'display_name'
	_order = 'id desc'

	fecha = fields.Date('Fecha', required=True, default=lambda *a: time.strftime('%Y-%m-%d'))
	name = fields.Char('Prestamo')
	display_name = fields.Char('Nombre para mostrar')
	fecha_primer_vencimiento = fields.Date('Fecha primer vencimiento', required=True, default=lambda *a: time.strftime('%Y-%m-%d'))
	monto_otorgado = fields.Float('Monto a financiar')
	cuenta_id = fields.Many2one('financiera.cuenta', 'Cuenta')
	cliente_id = fields.Many2one('res.partner', 'Cliente', related='cuenta_id.cliente_id')
	responsable_id = fields.Many2one('res.users', 'Responsable')
	plan_id = fields.Many2one('financiera.prestamo.plan', 'Plan de pagos', domain="[('state', '=', 'confirmado')]")
	periodo_id = fields.Selection([('mensual', 'Mensual'), ('diario', 'Diario'), ('semanal', 'Semanal'), ('quincenal', 'Quincenal'), ('bimestral', 'Bimestral'), ('trimestral', 'Trimestral'), ('cuatrimestral', 'Cuatrimestral'), ('semestral', 'Semestral'), ('anual', 'Anual')], string='Periodo', related='plan_id.forma_de_pago')
	cuotas = fields.Integer('Cuotas', related='plan_id.cuotas')
	tipo_de_amortizacion = fields.Selection([('sistema_directa', 'Sistema de tasa directa'), ('sistema_frances', 'Sistema frances'), ('sistema_aleman', 'Sistema aleman'), ('sistema_americano', 'Sistema americano')], string='Sistema de amortizacion', related='plan_id.tipo_de_amortizacion')
	cuota_ids = fields.One2many('financiera.prestamo.cuota', 'prestamo_id', 'Cuotas')
	state = fields.Selection([('borrador', 'Borrador'), ('confirmado', 'Confirmado'), ('activo', 'Activo'), ('cobrado', 'Cobrado'), ('cancelado', 'Cancelado')], string='Estado', readonly=True, default='borrador')
	saldo = fields.Float('Saldo', compute='_compute_saldo', readonly=True)
	tasa_periodo = fields.Float('Tasa del periodo', digits=(16, 6), compute='_compute_tasa_periodo')
	tasa_interna_de_rentabilidad = fields.Float('Tasa interna de rentabilidad', compute='_compute_tir')
	tasa_anual_equivalente = fields.Float('Tasa anual equivalente', compute='_compute_tasa_anual_equivalente')
	iva = fields.Boolean('Calcular IVA', default=False)
	iva_incluido = fields.Boolean('IVA incluido en el interes?', default=False)
	vat_tax_id = fields.Many2one('account.tax', 'Tasa de IVA', domain="[('type_tax_use', '=', 'sale')]")
	#Invoice
	date_invoice = fields.Date('Fecha de la factura')
	invoice_id = fields.Many2one('account.invoice', 'Factura', default=None)
	journal_invoice_id = fields.Many2one('account.journal', 'Diario de Factura', domain="[('type', '=', 'sale')]")
	iva_comision = fields.Float('IVA sobre comision', compute='_compute_iva_comision')
	iva_gastos = fields.Float('IVA sobre gestion', compute='_compute_iva_gastos')
	move_confirm_id = fields.Many2one('account.move', 'Asiento confirmacion prestamo')
	debt_move_line_ids = fields.One2many('account.move.line', 'cuota_id', 'Comisiones y Gastos', compute='_update_debt', default=None)
	#Payment
	payment_date = fields.Date('Fecha de pago')
	payment_group_id = fields.Many2one('account.payment.group', 'Comprobante de pago', default=None)
	payment_communication = fields.Char('Circular', default='Neto del Prestamo')
	journal_caja_id = fields.Many2one('account.journal', 'Metodo de Pago', domain="[('type', 'in', ('bank', 'cash'))]")
	comision_de_apertura = fields.Float('Comision de apertura')
	gastos_de_gestion = fields.Float('Gastos de gestion')
	neto_a_pagar = fields.Float('Neto del prestamo', compute='_compute_neto_a_pagar')
	neto_a_pagar_descontar_gastos = fields.Boolean("Descontar Gastos y Comision", default=False)

	@api.model
	def create(self, values):
		rec = super(FinancieraPrestamo, self).create(values)
		rec.update({
			'name': 'PMO ' + str(rec.cuenta_id.id).zfill(6) + '-'  + str(rec.id).zfill(8),
			'display_name': '['  + str(rec.id).zfill(8) + '] ' + rec.cliente_id.name,
			})
		return rec

	@api.one
	def unlink(self):
		if self.state != 'borrador':
			raise UserError("Solo puede borrar un Prestamo en estado Borrador.")
		else:
			return models.Model.unlink(self)

	@api.one
	def _compute_tir(self):
		cashflow = []
		cashflow.append(self.monto_otorgado * -1)
		for cuota_id in self.cuota_ids:
			cashflow.append(cuota_id.total-cuota_id.iva)
		if len(cashflow) >= self.plan_id.cuotas:
			self.tasa_interna_de_rentabilidad = np.irr(cashflow) * 100

	@api.one
	@api.onchange('cuenta_id')
	def asigned_responsable_cuenta(self):
		self.responsable_id = self.cuenta_id.responsable_id.id

#	@api.multi
#	def write(self, vals):
#		rec = super(FinancieraPrestamo, self).write(vals)
#		
#		return rec

	@api.one
	def _compute_tasa_anual_equivalente(self):
		if self.plan_id != False:
			r = self.plan_id.tasa_de_interes_anual
			f = self.plan_id.cuotas
			self.tasa_anual_equivalente = ((1 + r/f)**f-1) * 100

	@api.model
	@api.onchange('monto_otorgado', 'plan_id')
	def caclulate_comision_y_gestion(self):
		self.comision_de_apertura = self.monto_otorgado * self.plan_id.comision_de_apertura
		self.gastos_de_gestion = self.plan_id.gastos_de_gestion
		if self.plan_id.tipo_de_amortizacion == 'sistema_manual':
			self.monto_otorgado = self.plan_id.monto_a_financiar

	def caclulate_capital_cuotas_previas(self, nro_cuota):
		suma = 0.0
		for cuota in self.cuota_ids:
			if cuota.numero_cuota < nro_cuota:
				suma += cuota.capital
		return suma

	@api.one
	def _compute_saldo(self):
		saldo = 0
		for cuota in self.cuota_ids:
			saldo = saldo + cuota.saldo
		self.saldo = saldo

	@api.one
	def _compute_tasa_periodo(self):
		tasa = 0.0
		if self.plan_id.tasa_de_interes_anual > 0:
			tasa = self.plan_id.tasa_de_interes_anual
			tasa /= 12
		#else:
		#	raise ValidationError("El Plan de pagos no tiene configurada la tasa.")

		if self.plan_id.forma_de_pago == "diario":
			tasa /= 30.4167
		elif self.plan_id.forma_de_pago == "semanal":
			tasa /= 4.34524
		if self.plan_id.forma_de_pago == "quincenal":
			tasa /= 2.0
		elif self.plan_id.forma_de_pago == "bimestral":
			tasa *= 2
		elif self.plan_id.forma_de_pago == "trimestral":
			tasa *= 3
		elif self.plan_id.forma_de_pago == "cuatrimestral":
			tasa *= 4
		elif self.plan_id.forma_de_pago == "semestral":
			tasa *= 6
		elif self.plan_id.forma_de_pago == "anual":
			tasa *= 12
		self.tasa_periodo = tasa

	@api.one
	@api.onchange('comision_de_apertura')
	def _compute_iva_comision(self):
		if self.plan_id.iva_comision and self.vat_tax_id != None:
			self.iva_comision = self.comision_de_apertura * self.vat_tax_id.amount / 100
		else:
			self.iva_comision = 0

	@api.one
	@api.onchange('gastos_de_gestion')
	def _compute_iva_gastos(self):
		if self.plan_id.iva_gastos and self.vat_tax_id != None:
			self.iva_gastos = self.gastos_de_gestion * self.vat_tax_id.amount / 100
		else:
			self.iva_gastos = 0

	@api.one
	def _update_debt(self):
		if self.move_confirm_id != False and len(self.move_confirm_id.line_ids) > 1:
			if self.move_confirm_id.line_ids[0].credit > 0:# and not self.move_confirm_id.line_ids[0].reconciled:
				self.debt_move_line_ids = [self.move_confirm_id.line_ids[0].id]
			if self.move_confirm_id.line_ids[1].credit > 0:# and not self.move_confirm_id.line_ids[1].reconciled:
				self.debt_move_line_ids = [self.move_confirm_id.line_ids[1].id]

		for move_line_id in self.invoice_id.move_id.line_ids:
			if move_line_id.debit > 0:# and not move_line_id.reconciled:
				self.debt_move_line_ids = [move_line_id.id]

	@api.one
	def _debt_not_reconcilie(self):
		ret = []
		for ail_id in self.debt_move_line_ids:
			if not ail_id.reconciled:
				ret.append(ail_id.id)
		return ret

	def delete_cuotas_borrador(self):
		if self.state == 'borrador':
			for cuota_id in self.cuota_ids:
				cuota_id.unlink()
		else:
			raise UserError("Solo puede borrar cuotas de un Prestamo en borrador.")

	@api.one
	def calcular_cuotas_plan(self):
		if self.monto_otorgado <= 0:
			raise UserError("El prestamo debe ser mayor a cero.")
		else:	
			fecha_inicial = datetime.strptime(self.fecha_primer_vencimiento, "%Y-%m-%d")
			fpc_ids = []
			fecha_vencimiento = None
			cr = self.env.cr
			uid = self.env.uid
			#feriados_obj = self.pool.get('feriados.feriados.dia').search(cr, uid, [('date', '=', check_fecha)])
			#feriados_ids = feriados_obj.
			#for _id in cuotas_ids:
			#cuota_id = cuotas_obj.browse(cr, uid, _id)

			i = 0
			dias_no_habiles = 0
			self.delete_cuotas_borrador()
			while i < self.plan_id.cuotas:
				if i == 0:
					fecha_vencimiento = self.fecha_primer_vencimiento
					fecha_vencimiento_pre_semana = datetime.strptime(self.fecha_primer_vencimiento, "%Y-%m-%d") + timedelta(days=-7)
					fecha_vencimiento_pos_semana = datetime.strptime(self.fecha_primer_vencimiento, "%Y-%m-%d") + timedelta(days=7)
				else:
					fecha_relativa = None
					if self.plan_id.forma_de_pago == "mensual":
						fecha_relativa = relativedelta.relativedelta(months=i)
					if self.plan_id.forma_de_pago == "diario":
						while True:
							fecha_relativa = relativedelta.relativedelta(days=i+dias_no_habiles)
							check_fecha = fecha_inicial + fecha_relativa
							es_sabado = check_fecha.weekday() == 5
							es_domingo = check_fecha.weekday() == 6
							es_feriado = len(self.pool.get('feriados.feriados.dia').search(cr, uid, [('date', '=', check_fecha)])) > 0
							if self.plan_id.dias_de_cobro == 'laboral':
								#Se cobra de Lunes a Viernes
								if es_sabado or es_domingo or es_feriado:
									dias_no_habiles += 1
								else:
									break
							if self.plan_id.dias_de_cobro == 'laboral_extendida':
								#Se cobra de Lunes a Sabados
								if es_domingo or es_feriado:
									dias_no_habiles += 1
								else:
									break
							if self.plan_id.dias_de_cobro == 'todos':
								#Se cobra de Lunes a Lunes
								if es_feriado:
									dias_no_habiles += 1
								else:
									break
					elif self.plan_id.forma_de_pago == "semanal":
						fecha_relativa = relativedelta.relativedelta(weeks=i)
					if self.plan_id.forma_de_pago == "quincenal":
						fecha_relativa = relativedelta.relativedelta(weeks=i*2)
					elif self.plan_id.forma_de_pago == "bimestral":
						fecha_relativa = relativedelta.relativedelta(months=i*2)
					elif self.plan_id.forma_de_pago == "trimestral":
						fecha_relativa = relativedelta.relativedelta(months=i*3)
					elif self.plan_id.forma_de_pago == "cuatrimestral":
						fecha_relativa = relativedelta.relativedelta(months=i*4)
					elif self.plan_id.forma_de_pago == "semestral":
						fecha_relativa = relativedelta.relativedelta(months=i*6)
					elif self.plan_id.forma_de_pago == "anual":
						fecha_relativa = relativedelta.relativedelta(years=i)

					fecha_vencimiento = fecha_inicial + fecha_relativa
					fecha_vencimiento_pre_semana = fecha_inicial + fecha_relativa + timedelta(days=-7)
					fecha_vencimiento_pos_semana = fecha_inicial + fecha_relativa + timedelta(days=+7)
				fpc = {
						'numero_cuota': i+1,
						'display_numero_cuota': str(i+1).zfill(3),
						'fecha_vencimiento': fecha_vencimiento,
						'fecha_vencimiento_pre_semana': fecha_vencimiento_pre_semana,
						'fecha_vencimiento_pos_semana': fecha_vencimiento_pos_semana,
					}
				fpc_ids.append((0,0,fpc))
				i += 1
			self.cuota_ids = fpc_ids

	@api.one
	def cancelar_prestamo(self):
		#self.delete_cuotas_borrador()
		self.state = 'borrador'

	@api.one
	@api.onchange('neto_a_pagar_descontar_gastos','comision_de_apertura', 'gastos_de_gestion')
	def _compute_neto_a_pagar(self):
		if self.neto_a_pagar_descontar_gastos:
			self.neto_a_pagar = self.monto_otorgado - self.comision_de_apertura - self.iva_comision - self.gastos_de_gestion - self.iva_gastos
		else:
			self.neto_a_pagar = self.monto_otorgado

	@api.one
	def confirmar_prestamo(self):
		self.name = 'PMO ' + str(self.cuenta_id.id).zfill(6) + '-'  + str(self.id).zfill(8)
		self.display_name = '['  + str(self.id).zfill(8) + '] ' + self.cliente_id.name
		if len(self.cuota_ids) == 0:
			raise UserError("No puede confirmar un prestamo sin cuotas.")
		elif self.monto_otorgado <= 0:
			raise UserError("El prestamo debe ser de monto mayor a cero.")
		else:
			#Creamos asiento de acreditacion de credito al cliente
			aml = {
			    'name': "Capital otorgado",
			    'account_id': self.plan_id.capital_a_cobrar_id.default_debit_account_id.id,
			    'journal_id': self.plan_id.capital_a_cobrar_id.id,
			    'date': self.fecha,
			    'date_maturity': self.fecha,
			    'debit': self.monto_otorgado,
			}

			aml2 = {
			    'name': "Capital aprobado",
			    'account_id': self.cuenta_id.cliente_id.property_account_receivable_id.id,
			    'journal_id': self.plan_id.capital_a_cobrar_id.id,
			    'date': self.fecha,
			    'date_maturity': self.fecha,
			    'credit': self.monto_otorgado,
			    'partner_id': self.cuenta_id.cliente_id.id,
			}
			am_values = {
			    'journal_id': self.plan_id.capital_a_cobrar_id.id,
			    'partner_id': self.cuenta_id.cliente_id.id,
			    'state': 'draft',
			    'name': 'PRESTAMO-APROBADO/'+str(self.id).zfill(5),
			    'date': self.fecha,
			    'line_ids': [(0, 0, aml), (0, 0, aml2)],
			}
			new_move_id = self.env['account.move'].create(am_values)
			new_move_id.post()
			self.move_confirm_id = new_move_id.id
			self.state = 'confirmado'


	@api.multi
	def facturar_prestamo(self):
		cr = self.env.cr
		uid = self.env.uid

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'facturar_prestamo_view')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		#view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'financiera_prestamos', 'facturar_prestamo_view')
		#view_id = view_ref and view_ref[1] or False,
		self.date_invoice = datetime.now()
		return {
			'type': 'ir.actions.act_window',
			'name': 'Facturar Comision y Gestion',
			'view_mode': 'form',
			'view_type': 'form',
			'view_id': view_id,
			'res_model': 'financiera.prestamo',
			'nodestroy': True,
			'res_id': self.id, # assuming the many2one
			'target':'new',
		}

	@api.one
	def confirmar_factura(self):
		currency_id = self.env.user.company_id.currency_id.id
		# Create invoice line
		ail_ids = []
		vat_tax_id = False
		invoice_line_tax_ids = False
		if self.iva:
			vat_tax_id = self.vat_tax_id.id
			invoice_line_tax_ids = [(6, 0, [self.vat_tax_id.id])]
		if self.comision_de_apertura > 0:
			ail = {
			'name': "Comisiones por servicio",
			'quantity':1,
			'price_unit': self.comision_de_apertura,
			'vat_tax_id': vat_tax_id,
			'invoice_line_tax_ids': invoice_line_tax_ids,
			'report_invoice_line_tax_ids': invoice_line_tax_ids,
			'account_id': self.plan_id.cuenta_comision_de_apertura.id,
			}
			ail_ids.append((0,0,ail))
		# Create invoice line
		if self.gastos_de_gestion > 0:
			ail2 = {
				'name': "Gastos por cuenta del cliente.",
				'quantity':1,
				'price_unit': self.gastos_de_gestion,
				'vat_tax_id': vat_tax_id,
				'invoice_line_tax_ids': invoice_line_tax_ids,
				'report_invoice_line_tax_ids': invoice_line_tax_ids,
				'account_id': self.plan_id.cuenta_gastos_de_gestion.id,
			}
			ail_ids.append((0,0,ail2))
		if len(ail_ids) > 0:
			ai_values = {
			    'account_id': self.cuenta_id.cliente_id.property_account_receivable_id.id,
			    'partner_id': self.cuenta_id.cliente_id.id,
			    'journal_id': self.journal_invoice_id.id,
			    'currency_id': currency_id,
			    'company_id': 1,
			    'date': self.date_invoice,
			    'invoice_line_ids': ail_ids,
			}
			new_invoice_id = self.env['account.invoice'].create(ai_values)
			if self.plan_id.factura_validacion_automatica:
				new_invoice_id.signal_workflow('invoice_open')
			self.invoice_id = new_invoice_id.id
    
	@api.multi
	def ver_factura(self):
		#self.ensure_one()
		if len(self.invoice_id) == 0:
			raise UserError("No hay factura disponible.")
		else:
			action = self.env.ref('account.action_invoice_tree1')
			result = action.read()[0]
			form_view = self.env.ref('account.invoice_form')
			result['views'] = [(form_view.id, 'form')]
			result['res_id'] = self.invoice_id.id
			return result

	@api.multi
	def pagar_prestamo(self):
		cr = self.env.cr
		uid = self.env.uid

		view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'financiera_prestamos', 'confirmar_prestamo_view')
		view_id = view_ref and view_ref[1] or False,
		#this = self.browse(cr, uid, ids, context=context)[0]
		self.payment_date = datetime.now()
		return {
			'type': 'ir.actions.act_window',
			'name': 'Pagar Prestamo',
			'view_mode': 'form',
			'view_type': 'form',
			'view_id': view_id,
			'res_model': 'financiera.prestamo',
			'nodestroy': True,
			'res_id': self.id, # assuming the many2one
			'target':'new',
			#'flags': {'form': {'action_buttons': True}},
			#'context': context,
		}

	@api.one
	def confirmar_pagar_prestamo(self):
		for cuota_id in self.cuota_ids:
			cuota_id.state = 'activa'
		self.state = 'activo'
		
		currency_id = self.env.user.company_id.currency_id.id
		cr = self.env.cr
		uid = self.env.uid
		#Pago al cliente
		payment_method_obj = self.pool.get('account.payment.method')
		payment_method_id = payment_method_obj.search(cr, uid, [('code', '=', 'manual'), ('payment_type', '=', 'outbound')])[0]
		ap_values = {
			'payment_type': 'outbound',
			'payment_type_copy': 'outbound',			
			'partner_type': 'customer',
			'partner_id': self.cuenta_id.cliente_id.id,
			'amount': self.neto_a_pagar,
			'payment_date': self.payment_date,
			'journal_id': self.journal_caja_id.id,
			'payment_method_code': 'manual',
			'currency_id': currency_id,
			'payment_method_id': payment_method_id,
			'communication': self.payment_communication,
		}

		payment_group_receiptbook_obj = self.pool.get('account.payment.receiptbook')
		payment_group_receiptbook_id = payment_group_receiptbook_obj.search(cr, uid, [('sequence_type', '=', 'automatic'), ('partner_type', '=', 'customer')])[0]
		apg_values = {
			'payment_date': self.payment_date,
			'company_id': 1,
			'partner_id': self.cuenta_id.cliente_id.id,
			'currency_id': currency_id,
			'payment_ids': [(0,0,ap_values)],
			'receiptbook_id': payment_group_receiptbook_id,
			'partner_type': 'customer',
			'account_internal_type': 'receivable', #or payable
			'debt_move_line_ids': self._debt_not_reconcilie()[0],
		}
		new_payment_group_id = self.env['account.payment.group'].create(apg_values)
		new_payment_group_id.post()
		self.payment_group_id = new_payment_group_id.id

	@api.one
	def comprobar_estado_prestamo(self):
		cr = self.env.cr
		uid = self.env.uid
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')),
			('prestamo_id', '=', self.id),
		])
		if len(cuotas_ids) == 0:
			self.state = 'cobrado'


class FinancieraPrestamoCuota(models.Model):
	_name = 'financiera.prestamo.cuota'
	#_inherit = ['mail.thread', 'ir.needaction_mixin']

	_rec_name = 'display_name'
	_order = 'fecha_vencimiento asc'
	numero_cuota = fields.Integer('Numero de cuota', required=True)
	display_numero_cuota = fields.Char('Cuota')
	prestamo_id = fields.Many2one('financiera.prestamo', 'Prestamo', ondelete='cascade')
	cuenta_id = fields.Many2one('financiera.cuenta', 'Cuenta', related='prestamo_id.cuenta_id')
	cliente_id = fields.Many2one('res.partner', 'Cliente', related='prestamo_id.cuenta_id.cliente_id')
	responsable_id = fields.Many2one('res.users', 'Responsable', related='prestamo_id.responsable_id')
	display_name = fields.Char('Nombre')
	fecha_vencimiento = fields.Date('Fecha vencimiento', required=True)
	fecha_vencimiento_pre_semana = fields.Date('Fecha vencimiento')
	fecha_vencimiento_pos_semana = fields.Date('Fecha vencimiento')
	dias_de_gracia = fields.Integer('Dias de gracia')
	state = fields.Selection([('borrador', 'Borrador'), ('activa', 'Activa'), ('facturado', 'Facturado'), ('cobrada', 'Cobrada')], string='Estado', readonly=True, default='borrador')
	state_mora = fields.Selection([('normal', 'Normal'), ('preventiva', 'Preventiva'), ('moraTemprana', 'Mora temprana'), ('moraMedia', 'Mora media'), ('moraTardia', 'Mora tardia'), ('incobrable', 'Incobrable')], string='Estado', compute='_compute_state_mora', default='normal')
	saldo_capital = fields.Float('Saldo Capital', compute='_compute_saldo_capital')
	# Componentes del monto de la cuota
	capital = fields.Float('Capital', compute='_compute_capital')
	interes = fields.Float('Interes', compute='_compute_interes')
	cuota_pura = fields.Float('Cuota pura', compute='_compute_cuota_pura')
	iva = fields.Float('IVA', compute='_compute_iva')
	dias_punitorios = fields.Integer('Dias punitorios', compute='_compute_dias_punitorios')
	punitorios = fields.Float('Punitorios no facturados', compute='_compute_punitorios')
	punitorios_facturados = fields.Float('Punitorios facturados')
	punitorios_totales = fields.Float('Punitorios', compute='_compute_punitorios_totales')
	punitorios_fecha_hasta = fields.Date("Calcular punitorios hasta")
	calculo_punitorios = fields.Text('Calculo punitorios', compute='_compute_calculo_punitorios')
	otros_gastos = fields.Float('Otros gastos descuentos')
	otros_gastos_iva = fields.Boolean('Calcular IVA')
	otros_gastos_fecha = fields.Date("Fecha")
	otros_gastos_nuevo_importe = fields.Float('Importe')
	otros_gastos_journal_id = fields.Many2one('account.journal', 'Diario', domain="[('type', '=', 'general')]")
	otros_gastos_ids = fields.One2many('account.move.line', 'cuota_descuento_id', 'Otros descuentos')
	otros_gastos_tipo = fields.Selection([('gasto', 'Gastos al cliente'), ('descuento', 'Descuento al cliente')], string='Tipo', default='gasto')
	otros_gastos_journal2_id = fields.Many2one('account.journal', 'Diario', domain="[('type', '=', 'sale')]")
	otros_gastos_iva_monto = fields.Float('Otros gastos IVA', compute='_compute_otros_gatos_iva_monto')
	total = fields.Float('Monto cuota', compute='_compute_total')
	cobrado = fields.Float('Cobrado', readonly=True)
	saldo = fields.Float('Saldo cuota', compute='_compute_saldo')
	ultima_fecha_cobro = fields.Date('Ultima fecha de cobro', readonly=True)
	ultima_fecha_punitorios_facturados = fields.Date('Ultima fecha de punitorios facturados', readonly=True)	
	#cuota_proxima_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota proxima')
	#cuota_previa_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota previa')
	factura_validacion_automatica = fields.Boolean('Validacion automatica de factura')
	#Invoices
	invoice_ids = fields.One2many('account.invoice', 'cuota_id', 'Facturas', default=None)
	journal_invoice_id = fields.Many2one('account.journal', 'Diario de Factura', domain="[('type', '=', 'sale')]")
	date_invoice = fields.Date('Fecha de la factura')	
	invoice_init = fields.Boolean('Factura inicial', default=False)
	#Payment
	payment_group_ids = fields.One2many('account.payment.group', 'cuota_id', 'Comprobantes de pago', default=None)
	payment_communication = fields.Char('Circular', default='Pago cuota #')
	journal_caja_id = fields.Many2one('account.journal', 'Metodo de Pago', domain="[('type', 'in', ('bank', 'cash'))]")
	payment_date = fields.Date('Fecha de pago')
	payment_amount = fields.Float('Monto a cobrar')
	#Deuda
	debt_move_line_ids = fields.One2many('account.move.line', 'cuota_id', 'Deuda de cuota', compute='_update_debt', default=None)
	move_capital_id = fields.Many2one('account.move', 'Asiento de capital', default=None)

	@api.model
	def create(self, values):
		rec = super(FinancieraPrestamoCuota, self).create(values)
		rec.update({
			'display_name': '[' + str(rec.prestamo_id.id).zfill(8) + ']['  + rec.display_numero_cuota + '] ' + rec.cliente_id.name,
			'factura_validacion_automatica': rec.prestamo_id.plan_id.factura_validacion_automatica,
			})
		return rec

	@api.one
	def unlink(self):
		if self.state != 'borrador':
			raise UserError("Solo puede borrar una Cuota en estado Borrador.")
		else:
			return models.Model.unlink(self)

	@api.one
	def _compute_saldo_capital(self):
		if self.numero_cuota == 1:
			self.saldo_capital = self.prestamo_id.monto_otorgado
		else:
			self.saldo_capital = self.prestamo_id.monto_otorgado - self.prestamo_id.caclulate_capital_cuotas_previas(self.numero_cuota)

	@api.one
	def _compute_capital(self):
		tipo_de_amortizacion = self.prestamo_id.plan_id.tipo_de_amortizacion
		monto = self.prestamo_id.monto_otorgado
		tasa = self.prestamo_id.tasa_periodo
		cuotas = self.prestamo_id.plan_id.cuotas
		if tipo_de_amortizacion == 'sistema_frances':
			cuota = monto * (tasa / (1-(1+tasa)**-cuotas))
			self.capital = cuota * (1-tasa*(1-(1+tasa)**-(cuotas-self.numero_cuota+1))/ tasa)
		elif tipo_de_amortizacion == 'sistema_directa' or tipo_de_amortizacion == 'sistema_manual':
			if self.numero_cuota == self.prestamo_id.plan_id.cuotas:
				self.capital = monto - (round(monto / cuotas, 2) * (cuotas-1))
			else:
				self.capital = round(monto / cuotas, 2)
		elif tipo_de_amortizacion == 'sistema_aleman':
			self.capital = round(monto / cuotas, 2)
		elif tipo_de_amortizacion == 'sistema_americano':
			if self.numero_cuota == self.prestamo_id.plan_id.cuotas:
				self.capital = monto
			else:
				self.capital = 0

	@api.one
	def _compute_interes(self):
		tipo_de_amortizacion = self.prestamo_id.plan_id.tipo_de_amortizacion
		monto = self.prestamo_id.monto_otorgado
		tasa = self.prestamo_id.tasa_periodo
		cuotas = self.prestamo_id.plan_id.cuotas
		
		if tipo_de_amortizacion == 'sistema_frances':
			cuota = monto * (tasa / (1-(1+tasa)**-cuotas))
			self.interes = tasa * cuota * (1-(1+tasa)**-(cuotas-self.numero_cuota+1))/tasa
		elif tipo_de_amortizacion == 'sistema_manual':
			capital = round(monto / cuotas,2)
			self.interes = self.prestamo_id.plan_id.monto_cuota - self.capital
		elif tipo_de_amortizacion == 'sistema_directa':
			tasa_periodo = self.prestamo_id.tasa_periodo
			if self.numero_cuota == self.prestamo_id.plan_id.cuotas:
				interes_previo = round(monto * tasa_periodo, 2) * (cuotas-1)
				self.interes = monto * (tasa_periodo * cuotas) - interes_previo
			else:
				self.interes = round(monto * tasa_periodo, 2)
		elif tipo_de_amortizacion == 'sistema_aleman':
			self.interes = (monto / cuotas) * (cuotas - self.numero_cuota+1) * tasa
		elif tipo_de_amortizacion == 'sistema_americano':
			self.interes = monto * tasa
		
		if self.prestamo_id.iva_incluido:
			self.interes /= (1 + self.prestamo_id.vat_tax_id.amount / 100)

	@api.one
	def _compute_cuota_pura(self):
		self.cuota_pura = self.capital + self.interes

	@api.one
	def _compute_iva(self):
		if self.prestamo_id.iva:
			self.iva = self.interes * self.prestamo_id.vat_tax_id.amount / 100
	
	@api.one
	@api.onchange('punitorios_fecha_hasta')
	def _compute_dias_punitorios(self):
		if self.state == 'cobrada':
			self.dias_punitorios = 0
		else:
			self.dias_punitorios = 0
			if self.ultima_fecha_punitorios_facturados == False:
				self.ultima_fecha_punitorios_facturados = self.fecha_vencimiento
			fecha_desde = datetime.strptime(str(self.ultima_fecha_punitorios_facturados), "%Y-%m-%d")
			if self.punitorios_fecha_hasta == False:
				fecha_hasta = datetime.now()
			else:
				fecha_hasta = datetime.strptime(self.punitorios_fecha_hasta, "%Y-%m-%d")
			if fecha_hasta > fecha_desde:
				diferencia = fecha_hasta - fecha_desde
				self.dias_punitorios = diferencia.days

	@api.one
	@api.onchange('punitorios_fecha_hasta')
	def _compute_punitorios(self):
		tasa_punitorios_diaria = self.prestamo_id.plan_id.tasa_mensual_de_punitorios / 30.4167
		if self.state == 'cobrada':
			self.punitorios = 0
		else:
			if self.prestamo_id.plan_id.tipo_de_amortizacion == 'sistema_manual':
				self.punitorios = self.prestamo_id.plan_id.monto_punitorio_diario * self.dias_punitorios
			else:
				self.punitorios = (self.capital + self.interes + self.iva - self.cobrado) * self.dias_punitorios * tasa_punitorios_diaria

	@api.one
	def _compute_punitorios_totales(self):
		#if self.state == 'cobrada':
		#self.punitorios_totales = 0
		#else:
		self.punitorios_totales = self.punitorios_facturados + self.punitorios

	@api.one
	def _compute_calculo_punitorios(self):
		tasa_punitorios_diaria = self.prestamo_id.plan_id.tasa_mensual_de_punitorios / 30.4167
		self.calculo_punitorios = str(round(tasa_punitorios_diaria, 8)) + "  ....		" + str(self.prestamo_id.plan_id.tasa_mensual_de_punitorios) + " / 30.4167 (tasa mensual punitorios / dias por mes)\n"
		self.calculo_punitorios += "x " + str(round(self.capital+self.interes+self.iva,2)) + "  ....		" + str(round(self.capital,2)) + " + " + str(round(self.interes,2)) + " + " + str(round(self.iva,2)) + " (capital + interes + iva)\n"
		self.calculo_punitorios += "x " + str(self.dias_punitorios) + "          ....		dias de punitorios"

	@api.one
	def _compute_total(self):
		self.total = round(self.capital,2) + round(self.interes,2) + round(self.iva,2) + round(self.punitorios_totales,2) + round(self.otros_gastos,2)

	@api.one
	def _compute_saldo(self):
		if self.state == 'cobrada':
			self.saldo = 0
		else:
			self.saldo = self.total - self.cobrado

	@api.one
	def _compute_state_mora(self):
		if self.state == 'cobrada':
			fecha_actual = datetime.strptime(self.ultima_fecha_cobro, "%Y-%m-%d")
		else:
			fecha_actual = datetime.now()

		configuracion_id = self.env['financiera.configuracion'].browse(1)
		if self.prestamo_id.plan_id.dias_preventivo >= 0:
			dias_preventivo = self.prestamo_id.plan_id.dias_preventivo
		elif configuracion_id.dias_preventivo:
			dias_preventivo = configuracion_id.dias_preventivo

		if self.prestamo_id.plan_id.dias_moraTemprana >= 0:
			dias_moraTemprana = self.prestamo_id.plan_id.dias_moraTemprana
		elif configuracion_id.dias_moraTemprana:
			dias_moraTemprana = configuracion_id.dias_moraTemprana

		if self.prestamo_id.plan_id.dias_moraMeida >= 0:
			dias_moraMeida = self.prestamo_id.plan_id.dias_moraMeida
		elif configuracion_id.dias_moraMeida:
			dias_moraMeida = configuracion_id.dias_moraMeida

		if self.prestamo_id.plan_id.dias_moraTardia >= 0:
			dias_moraTardia = self.prestamo_id.plan_id.dias_moraTardia
		elif configuracion_id.dias_moraTardia:
			dias_moraTardia = configuracion_id.dias_moraTardia

		if self.prestamo_id.plan_id.dias_incobrable >= 0:
			dias_incobrable = self.prestamo_id.plan_id.dias_incobrable
		elif configuracion_id.dias_incobrable:
			dias_incobrable = configuracion_id.dias_incobrable

		fecha_vencimiento = datetime.strptime(self.fecha_vencimiento, "%Y-%m-%d")
		fecha_preventiva = fecha_vencimiento - timedelta(days=dias_preventivo)
		fecha_moraTemprana = fecha_vencimiento + timedelta(days=dias_moraTemprana)
		fecha_moraMedia = fecha_vencimiento + timedelta(days=dias_moraMeida)
		fecha_moraTardia = fecha_vencimiento + timedelta(days=dias_moraTardia)
		fecha_incobrable = fecha_vencimiento + timedelta(days=dias_incobrable)
 
		if fecha_actual < fecha_preventiva:
			self.state_mora = 'normal'
		elif fecha_actual >= fecha_preventiva and fecha_actual < fecha_moraTemprana:
			self.state_mora = 'preventiva'
		elif fecha_actual >= fecha_moraTemprana and fecha_actual < fecha_moraMedia:
			self.state_mora = 'moraTemprana'
		elif fecha_actual >= fecha_moraMedia and fecha_actual < fecha_moraTardia:
			self.state_mora = 'moraMedia'
		elif fecha_actual >= fecha_moraTardia and fecha_actual < fecha_incobrable:
			self.state_mora = 'moraTardia'
		elif fecha_actual >= fecha_incobrable:
			self.state_mora = 'incobrable'

	@api.one
	@api.onchange('otros_gastos_nuevo_importe')
	def _compute_otros_gatos_iva_monto(self):
		if self.otros_gastos_iva:
			self.otros_gastos_iva_monto = round(self.otros_gastos_nuevo_importe * self.prestamo_id.vat_tax_id.amount / 100, 2)
		else:
			self.otros_gastos_iva_monto = 0

	@api.one
	def _update_debt(self):
		if len(self.move_capital_id.line_ids) > 1:
			if self.move_capital_id.line_ids[0].debit > 0:# and not self.move_capital_id.line_ids[0].reconciled:
				self.debt_move_line_ids = [self.move_capital_id.line_ids[0].id]
			if self.move_capital_id.line_ids[1].debit > 0:# and not self.move_capital_id.line_ids[1].reconciled:
				self.debt_move_line_ids = [self.move_capital_id.line_ids[1].id]

		for invoice_id in self.invoice_ids:
			for move_line_id in invoice_id.move_id.line_ids:
				if move_line_id.debit > 0:# and not move_line_id.reconciled:
					self.debt_move_line_ids = [move_line_id.id]

		for move_line_id in self.otros_gastos_ids:
				if move_line_id.credit > 0:# and not move_line_id.reconciled:
					self.debt_move_line_ids = [move_line_id.id]

	@api.one
	def _debt_not_reconcilie(self):
		ret = []
		for ail_id in self.debt_move_line_ids:
			if not ail_id.reconciled:
				ret.append(ail_id.id)
		return ret

	@api.one
	def facturar_y_pagar(self, amount, journal_id, date):
		# Si esta en activa hay que generar y validar la factura de la cuota
		if not self.invoice_init or self.punitorios > 0:
			self.date_invoice = datetime.now()
			self.punitorios_fecha_hasta = date
			configuracion_id = self.env['financiera.configuracion'].browse(1)
			self.journal_invoice_id = configuracion_id.journal_invoice_id.id
			self.factura_validacion_automatica = True
			self.confirmar_factura_cuota()

		# Si tiene facturas pendientes en borrador las validamos
		for invoice_id in self.invoice_ids:
			if invoice_id.state == 'draft':
				invoice_id.signal_workflow('invoice_open')

		# Comenzamos con el pago - Seteamos valores iniciales
		self.payment_date = date
		self.payment_amount = amount
		self.payment_communication = "Pago prestamo #"+ str(self.id)
		self.journal_caja_id = journal_id.id
		self.confirmar_pagar_cuota()



	@api.multi
	def facturar_cuota(self):
		self.ensure_one()
		if self.invoice_init and self.punitorios == 0:
			raise UserError("No tiene nada para facturar.")
		else:
			cr = self.env.cr
			uid = self.env.uid
			view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'financiera_prestamos', 'facturar_cuota_view')
			view_id = view_ref and view_ref[1] or False,
			self.date_invoice = datetime.now()
			self.punitorios_fecha_hasta = datetime.now()

			configuracion_id = self.env['financiera.configuracion'].browse(1)
			self.journal_invoice_id = configuracion_id.journal_invoice_id.id
			return {
				'type': 'ir.actions.act_window',
				'name': 'Facturar Cuota',
				'view_mode': 'form',
				'view_type': 'form',
				'view_id': view_id,
				'res_model': 'financiera.prestamo.cuota',
				'nodestroy': True,
				'res_id': self.id,
				'target':'new',
			}

	@api.one
	def confirmar_factura_cuota(self):
		currency_id = self.env.user.company_id.currency_id.id
		ail_ids = []
		vat_tax_id = False
		invoice_line_tax_ids = False

		if self.prestamo_id.iva:
			vat_tax_id = self.prestamo_id.vat_tax_id.id
			invoice_line_tax_ids = [(6, 0, [self.prestamo_id.vat_tax_id.id])]
		if not self.invoice_init:
			#Generamos asiento del capital adeudado al cliente
			aml = {
			    'name': "Prestamo " + str(self.prestamo_id.id) + " - Capital cuota "+str(self.numero_cuota),
			    'account_id': self.prestamo_id.plan_id.capital_a_cobrar_id.default_debit_account_id.id,
			    'journal_id': self.prestamo_id.plan_id.capital_a_cobrar_id.id,
			    'date': self.date_invoice,
			    'date_maturity': self.fecha_vencimiento,
			    'credit': self.capital,
			}

			aml2 = {
			    'name': "Prestamo " + str(self.prestamo_id.id) + " - Capital cuota "+str(self.numero_cuota),
			    'account_id': self.prestamo_id.cuenta_id.cliente_id.property_account_receivable_id.id,
			    'journal_id': self.prestamo_id.plan_id.capital_a_cobrar_id.id,
			    'date': self.date_invoice,
			    'date_maturity': self.fecha_vencimiento,
			    'debit': self.capital,
			    'partner_id': self.prestamo_id.cuenta_id.cliente_id.id,
			}
			am_values = {
			    'journal_id': self.prestamo_id.plan_id.capital_a_cobrar_id.id,
			    'partner_id': self.prestamo_id.cuenta_id.cliente_id.id,
			    'name': 'CAPITAL/PRESTAMO-'+str(self.prestamo_id.id)+'/CUOTA-'+str(self.numero_cuota),
			    'date': self.date_invoice,
			    'line_ids': [(0, 0, aml), (0, 0, aml2)],
			}
			new_move_id = self.env['account.move'].create(am_values)
			new_move_id.post()
			self.move_capital_id = new_move_id.id
			self.invoice_init = True

			# Create invoice line
			# Intereses sobre capital
			ail = {
			    'name': "Interes por prestamo de dinero",
			    'quantity': 1,
			    'price_unit': self.interes,
			    'vat_tax_id': vat_tax_id,
			    'invoice_line_tax_ids': invoice_line_tax_ids,
			    'report_invoice_line_tax_ids': invoice_line_tax_ids,
			    'account_id': self.journal_invoice_id.default_debit_account_id.id,
			}
			ail_ids.append((0,0,ail))

		# Create invoice line
		if self.punitorios > 0:
			ail2 = {
			    'name': "Otros Intereses",
			    'quantity': 1,
			    'price_unit': self.punitorios,
			    'vat_tax_id': vat_tax_id,
			    'invoice_line_tax_ids': invoice_line_tax_ids,
			    'report_invoice_line_tax_ids': invoice_line_tax_ids,
			    'account_id': self.journal_invoice_id.default_debit_account_id.id,
			}
			ail_ids.append((0,0,ail2))
			self.punitorios_facturados += self.punitorios
			self.ultima_fecha_punitorios_facturados = self.punitorios_fecha_hasta
			self.punitorios_fecha_hasta = False
		ai_values = {
			'name': "Prestamo " + str(self.prestamo_id.id) + " - Interes cuota numero " + str(self.numero_cuota),
		    'account_id': self.cuenta_id.cliente_id.property_account_receivable_id.id,
		    'partner_id': self.cuenta_id.cliente_id.id,
		    'journal_id': self.journal_invoice_id.id,
		    'currency_id': currency_id,
		    'company_id': 1,
		    'date': self.date_invoice,
		    'invoice_line_ids': ail_ids,
		}
		new_invoice_id = self.env['account.invoice'].create(ai_values)
		if self.factura_validacion_automatica:
			new_invoice_id.signal_workflow('invoice_open')
		self.invoice_ids = [new_invoice_id.id]
		self.state = 'facturado'
		self.date_invoice = False

	@api.multi
	def pagar_cuota(self):
		invoice_validate = True
		for invoice_id in self.invoice_ids:
			if invoice_id.state == 'draft':
				invoice_validate = False
				break
		if invoice_validate == False:
			raise UserError("Hay facturas aun no validadas.")
		else:
			cr = self.env.cr
			uid = self.env.uid
			view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'financiera_prestamos', 'pagar_prestamo_cuota_view')
			view_id = view_ref and view_ref[1] or False,

			self.payment_date = datetime.now()
			self.payment_amount = self.saldo - self.punitorios
			self.payment_communication = "Pago prestamo #"+ str(self.id)
			return {
				'type': 'ir.actions.act_window',
				'name': 'Registrar Pago Cuota',
				'view_mode': 'form',
				'view_type': 'form',
				'view_id': view_id,
				'res_model': 'financiera.prestamo.cuota',
				'nodestroy': True,
				'res_id': self.id, # assuming the many2one
				'target':'new',
			}

	@api.one
	def confirmar_pagar_cuota(self):
		currency_id = self.env.user.company_id.currency_id.id
		cr = self.env.cr
		uid = self.env.uid

		#Pago del cliente
		payment_method_obj = self.pool.get('account.payment.method')
		payment_method_id = payment_method_obj.search(cr, uid, [('code', '=', 'manual'), ('payment_type', '=', 'inbound')])[0]
		ap_values = {
			'payment_type': 'inbound',
			'partner_type': 'customer',
			'partner_id': self.cuenta_id.cliente_id.id,
			'amount': self.payment_amount,
			'payment_date': self.payment_date,
			'journal_id': self.journal_caja_id.id,
			'payment_method_code': 'manual',
			'currency_id': currency_id,
			'payment_method_id': payment_method_id,
			'communication': self.payment_communication,
		}
		payment_group_receiptbook_obj = self.pool.get('account.payment.receiptbook')
		payment_group_receiptbook_id = payment_group_receiptbook_obj.search(cr, uid, [('sequence_type', '=', 'automatic'), ('partner_type', '=', 'customer')])[0]
		apg_values = {
			'payment_date': self.payment_date,
			'company_id': 1,
			'partner_id': self.cuenta_id.cliente_id.id,
			'currency_id': currency_id,
			'payment_ids': [(0,0,ap_values)],
			'receiptbook_id': payment_group_receiptbook_id,
			'partner_type': 'customer',
			'account_internal_type': 'receivable', #or payable
			'debt_move_line_ids': self._debt_not_reconcilie()[0],
		}
		new_payment_group_id = self.env['account.payment.group'].create(apg_values)
		new_payment_group_id.post()
		self.payment_group_ids = [new_payment_group_id.id]
		self.cobrado += self.payment_amount
		self.ultima_fecha_cobro = self.payment_date
		if round(self.saldo, 2) == 0:
			self.state = 'cobrada'
			self.prestamo_id.comprobar_estado_prestamo()

	@api.multi
	def otros_gastos_cuota(self):
		cr = self.env.cr
		uid = self.env.uid
		view_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'financiera_prestamos', 'otros_gastos_cuota_view')
		view_id = view_ref and view_ref[1] or False,

		self.otros_gastos_fecha = datetime.now()
		self.otros_gastos_iva = self.prestamo_id.iva
		return {
			'type': 'ir.actions.act_window',
			'name': 'Aplicar Comision o Descuentos',
			'view_mode': 'form',
			'view_type': 'form',
			'view_id': view_id,
			'res_model': 'financiera.prestamo.cuota',
			'nodestroy': True,
			'res_id': self.id, # assuming the many2one
			'target':'new',
		}

	@api.one
	def confirmar_otros_gastos(self):
		currency_id = self.env.user.company_id.currency_id.id
		cr = self.env.cr
		uid = self.env.uid

		aml_ids = []
		vat_tax_id = False
		invoice_line_tax_ids = False
		if self.prestamo_id.iva and self.otros_gastos_iva:
			vat_tax_id = self.prestamo_id.vat_tax_id.id
			invoice_line_tax_ids = [(6, 0, [self.prestamo_id.vat_tax_id.id])]

		if self.otros_gastos_nuevo_importe == 0:
			raise UserError("No se puede generar un gasto ni un descuento al cliente. El monto debe ser distinto de cero.")
		elif self.otros_gastos_tipo == 'gasto':
			#Creamos el gasto adicional al cliente mediante una factura
			self.otros_gastos += self.otros_gastos_nuevo_importe + self.otros_gastos_iva_monto
			ail = {
			    'name': "Otros Gastos",
			    'quantity': 1,
			    'price_unit': self.otros_gastos_nuevo_importe,
			    'vat_tax_id': vat_tax_id,
			    'invoice_line_tax_ids': invoice_line_tax_ids,
			    'report_invoice_line_tax_ids': invoice_line_tax_ids,
			    'account_id': self.otros_gastos_journal2_id.default_debit_account_id.id,
			}
			ai_values = {
				'name': "Prestamo " + str(self.prestamo_id.id) + " - Otros cargos cuota numero " + str(self.numero_cuota),
			    'account_id': self.cuenta_id.cliente_id.property_account_receivable_id.id,
			    'partner_id': self.cuenta_id.cliente_id.id,
			    'journal_id': self.otros_gastos_journal2_id.id,
			    'currency_id': currency_id,
			    'company_id': 1,
			    'date': self.otros_gastos_fecha,
			    'invoice_line_ids': [(0,0,ail)],
			}
			new_invoice_id = self.env['account.invoice'].create(ai_values)
			if self.prestamo_id.plan_id.factura_validacion_automatica:
				new_invoice_id.signal_workflow('invoice_open')
			self.invoice_ids = [new_invoice_id.id]
		elif self.otros_gastos_tipo == 'descuento':
			#Creamos el descuento adicional
			#Lo registramos en la cuenta de descuentos otorgados
			self.otros_gastos -= self.otros_gastos_nuevo_importe
			aml = {
			    'name': "Descuentos varios",
			    'account_id': self.otros_gastos_journal_id.default_debit_account_id.id,
			    'journal_id': self.otros_gastos_journal_id.id,
			    'date': self.otros_gastos_fecha,
			    'date_maturity': self.otros_gastos_fecha,
			    'debit': self.otros_gastos_nuevo_importe,
			}
			aml_ids.append((0,0,aml))
			#Lo registramos en la cuenta del cliente a favor de el
			aml2 = {
			    'name': "Otros descuentos",
			    'account_id': self.cuenta_id.cliente_id.property_account_receivable_id.id,
			    'journal_id': self.otros_gastos_journal_id.id,
			    'date': self.otros_gastos_fecha,
			    'date_maturity': self.otros_gastos_fecha,
			    'credit': self.otros_gastos_nuevo_importe,
			    'partner_id': self.cuenta_id.cliente_id.id,
			}
			aml_ids.append((0,0,aml2))

			am_values = {
			    'journal_id': self.otros_gastos_journal_id.id,
			    'partner_id': self.cuenta_id.cliente_id.id,
			    'state': 'draft',
			    'name': 'OTROS-DESCUENTOS/'+str(self.id),
			    'date': self.otros_gastos_fecha,
			    'line_ids': aml_ids,
			}
			new_move_id = self.env['account.move'].create(am_values)
			new_move_id.post()
			if self.saldo == 0:
				self.state = 'cobrada'
			if new_move_id.line_ids[0].credit > 0:
				self.otros_gastos_ids = [new_move_id.line_ids[0].id]
			if new_move_id.line_ids[1].credit > 0:
				self.otros_gastos_ids = [new_move_id.line_ids[1].id]
		self.otros_gastos_nuevo_importe = 0


	def cuotas_en_preventiva(self, cr, uid, ids, context=None):
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')), 
			])
		ret = []
		for _id in cuotas_ids:
			cuota_id = cuotas_obj.browse(cr, uid, _id, context=context)
			if cuota_id.state_mora == 'preventiva':
				ret.append(cuota_id.id)

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		view_form_id = model_obj.get_object_reference(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		return {
			'domain': "[('id', 'in', ["+','.join(map(str, ret))+"])]",
			'name': ('Cuotas en Preventiva'),
			'view_type': 'form',
			'view_mode': 'tree,form',
			'res_model': 'financiera.prestamo.cuota',
			'view_ids': [view_id, view_form_id[1]],
			'type': 'ir.actions.act_window',
		}

	def cuotas_en_moratemprana(self, cr, uid, ids, context=None):
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')), 
			])
		ret = []
		for _id in cuotas_ids:
			cuota_id = cuotas_obj.browse(cr, uid, _id, context=context)
			if cuota_id.state_mora == 'moraTemprana':
				ret.append(cuota_id.id)

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		view_form_id = model_obj.get_object_reference(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		return {
			'domain': "[('id', 'in', ["+','.join(map(str, ret))+"])]",
			'name': ('Cuotas en Mora Temprana'),
			'view_type': 'form',
			'view_mode': 'tree,form',
			'res_model': 'financiera.prestamo.cuota',
			'view_ids': [view_id, view_form_id[1]],
			'type': 'ir.actions.act_window',
		}

	def cuotas_en_moramedia(self, cr, uid, ids, context=None):
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')), 
			])
		ret = []
		for _id in cuotas_ids:
			cuota_id = cuotas_obj.browse(cr, uid, _id, context=context)
			if cuota_id.state_mora == 'moraMedia':
				ret.append(cuota_id.id)

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		view_form_id = model_obj.get_object_reference(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		return {
			'domain': "[('id', 'in', ["+','.join(map(str, ret))+"])]",
			'name': ('Cuotas en Mora Media'),
			'view_type': 'form',
			'view_mode': 'tree,form',
			'res_model': 'financiera.prestamo.cuota',
			'view_ids': [view_id, view_form_id[1]],
			'type': 'ir.actions.act_window',
		}

	def cuotas_en_moratardia(self, cr, uid, ids, context=None):
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')), 
			])
		ret = []
		for _id in cuotas_ids:
			cuota_id = cuotas_obj.browse(cr, uid, _id, context=context)
			if cuota_id.state_mora == 'moraTardia':
				ret.append(cuota_id.id)

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		view_form_id = model_obj.get_object_reference(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		return {
			'domain': "[('id', 'in', ["+','.join(map(str, ret))+"])]",
			'name': ('Cuotas en Mora Tardia'),
			'view_type': 'form',
			'view_mode': 'tree,form',
			'res_model': 'financiera.prestamo.cuota',
			'view_ids': [view_id, view_form_id[1]],
			'type': 'ir.actions.act_window',
		}

	def cuotas_incobrable(self, cr, uid, ids, context=None):
		cuotas_obj = self.pool.get('financiera.prestamo.cuota')
		cuotas_ids = cuotas_obj.search(cr, uid, [
			('state', 'in', ('activa', 'facturado')), 
			])
		ret = []
		for _id in cuotas_ids:
			cuota_id = cuotas_obj.browse(cr, uid, _id, context=context)
			if cuota_id.state_mora == 'incobrable':
				ret.append(cuota_id.id)

		model_obj = self.pool.get('ir.model.data')
		data_id = model_obj._get_id(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		view_id = model_obj.browse(cr, uid, data_id, context=None).res_id

		view_form_id = model_obj.get_object_reference(cr, uid, 'financiera_prestamos', 'financiera_prestamo_cuota_form')
		return {
			'domain': "[('id', 'in', ["+','.join(map(str, ret))+"])]",
			'name': ('Cuotas Incobrables'),
			'view_type': 'form',
			'view_mode': 'tree,form',
			'res_model': 'financiera.prestamo.cuota',
			'view_ids': [view_id, view_form_id[1]],
			'type': 'ir.actions.act_window',
		}

class FinancieraPrestamoPlan(models.Model):
	_name = 'financiera.prestamo.plan'
	_description = 'Parametros para el calculo de cuotas'

	name = fields.Char('Nombre', size=64)
	codigo = fields.Char('Codigo', size=10)
	#tipo = fields.Many2one('financiera.prestamo.plan.tipo', 'Tipo')
	active = fields.Boolean('Activo', default=True)
	recibo_de_sueldo = fields.Boolean('Requiere recibo de sueldo?', default=False)
	
	forma_de_pago = fields.Selection([('mensual', 'Mensual'), ('diario', 'Diario'), ('semanal', 'Semanal'), ('quincenal', 'Quincenal'), ('bimestral', 'Bimestral'), ('trimestral', 'Trimestral'), ('cuatrimestral', 'Cuatrimestral'), ('semestral', 'Semestral'), ('anual', 'Anual')], string='Periodo', select=True, default='mensual')
	tipo_de_amortizacion = fields.Selection([('sistema_manual', 'Manual'),('sistema_directa', 'Amortizacion de tasa directa'), ('sistema_frances', 'Amortizacion frances'), ('sistema_aleman', 'Amortizacion aleman'), ('sistema_americano', 'Amortizacion americano')], string='Sistema de Amortizacion', select=True)
	dias_entre_vencimientos = fields.Integer('Dias entre vencimientos')
	cuotas = fields.Integer('Cuotas')
	tasa_de_interes_anual = fields.Float('Tasa de interes nominal anual', digits=(16,4))
	tasa_de_interes_mensual = fields.Float('Tasa de interes mensual', digits=(16,4), readonly=True, compute='_compute_tasa_mensual')
	tasa_mensual_de_punitorios = fields.Float('Tasa mensual de punitorios', digits=(16,4))
	dias_de_gracia_punitorios = fields.Integer('Dias de gracia para punitorios')
	factura_validacion_automatica = fields.Boolean('Validacion automatica en facturas', help="Solo es recomendable cuando no se utiliza Factura electronica AFIP.", default=False)
	iva = fields.Boolean('Calcular IVA')
	iva_incluido = fields.Boolean('IVA incluido en el interes?')
	proporcional_primer_cuota = fields.Boolean('Interes proporcional de la primer cuota')
	capital_a_cobrar_id = fields.Many2one('account.journal', 'Capital a cobrar', domain="[('type', '=', 'general')]")
	comision_de_apertura = fields.Float('Tasa de comision de apertura', digits=(16,4))
	cuenta_comision_de_apertura = fields.Many2one('account.account', 'Cuenta comision (ingreso)')
	iva_comision = fields.Boolean('Calcular IVA sobre la comision de apertura?')
	gastos_de_gestion = fields.Float('Comision de gestion')
	cuenta_gastos_de_gestion = fields.Many2one('account.account', 'Cuenta comision de gestion (ingreso)')
	iva_gastos = fields.Boolean('Calcular IVA sobre la comision de gestion?')	
	state = fields.Selection([('borrador', 'Borrador'), ('confirmado', 'Confirmado'), ('obsoleto', 'Obsoleto')], string='Estado', readonly=True, default='borrador')
	dias_preventivo = fields.Integer('Dias para preventiva', help="Es la cantidad de dias antes del vencimiento de la cuota.")
	dias_moraTemprana = fields.Integer('Dias para mora temprana')
	dias_moraMeida = fields.Integer('Dias para mora media')
	dias_moraTardia = fields.Integer('Dias para mora tardia')
	dias_incobrable = fields.Integer('Dias para incobrable')

	dias_de_cobro = fields.Selection([('laboral', 'Lunes a Viernes'),('laboral_extendida', 'Lunes a Sabado'),('todos', 'Todos los dias')], string='Dias de cobro', select=True)
	monto_cuota = fields.Float('Monto de la cuota')
	monto_punitorio_diario = fields.Float('Punitorios por dia')
	monto_a_financiar = fields.Float('Monto a financiar')

	@api.model
	def default_get(self, fields):
		rec = super(FinancieraPrestamoPlan, self).default_get(fields)
		context = dict(self._context or {})

		configuracion_id = self.env['financiera.configuracion'].browse(1)

		rec['dias_preventivo'] = configuracion_id.dias_preventivo
		rec['dias_moraTemprana'] = configuracion_id.dias_moraTemprana
		rec['dias_moraMeida'] = configuracion_id.dias_moraMeida
		rec['dias_moraTardia'] = configuracion_id.dias_moraTardia
		rec['dias_incobrable'] = configuracion_id.dias_incobrable

		if len(configuracion_id.capital_a_cobrar_id) > 0:
			rec['capital_a_cobrar_id'] = configuracion_id.capital_a_cobrar_id.id
		if len(configuracion_id.cuenta_comision_de_apertura) > 0:
			rec['cuenta_comision_de_apertura'] = configuracion_id.cuenta_comision_de_apertura.id
		if len(configuracion_id.cuenta_gastos_de_gestion) > 0:
			rec['cuenta_gastos_de_gestion'] = configuracion_id.cuenta_gastos_de_gestion.id
		rec['factura_validacion_automatica'] = configuracion_id.factura_validacion_automatica
		return rec

	@api.one
	@api.onchange('tasa_de_interes_anual')
	def _compute_tasa_mensual(self):
		self.tasa_de_interes_mensual = self.tasa_de_interes_anual / 12

	@api.one
	def confirmar_plan(self):
		self.state = 'confirmado'

	@api.one
	def depreciar_plan(self):
		self.state = 'obsoleto'

	@api.one
	def editar_plan(self):
		self.state = 'borrador'

class FinancieraConfiguracion(models.Model):
	_name = 'financiera.configuracion'

	name = fields.Char('Nombre', defualt='Configuracion general', readonly=True, required=True)
	dias_preventivo = fields.Integer('Dias para preventiva', help="Es la cantidad de dias antes del vencimiento de la cuota.")
	dias_moraTemprana = fields.Integer('Dias para mora temprana')
	dias_moraMeida = fields.Integer('Dias para mora media')
	dias_moraTardia = fields.Integer('Dias para mora tardia')
	dias_incobrable = fields.Integer('Dias para incobrable')
	capital_a_cobrar_id = fields.Many2one('account.journal', 'Capital a cobrar', domain="[('type', '=', 'general')]")
	journal_invoice_id = fields.Many2one('account.journal', 'Diario de factura', domain="[('type', '=', 'sale')]")
	cuenta_comision_de_apertura = fields.Many2one('account.account', 'Cuenta comision (ingreso)')
	cuenta_gastos_de_gestion = fields.Many2one('account.account', 'Cuenta gastos de gestion (ingreso)')
	factura_validacion_automatica = fields.Boolean('Validacion automatica en facturas', help="Solo es recomendable cuando no se utiliza Factura electronica AFIP.", default=False)


class ExtendsInvoice(models.Model):
	_name = 'account.invoice'
	_inherit = 'account.invoice'

	cuota_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota')

class ExtendsPaymentGroup(models.Model):
	_name = 'account.payment.group'
	_inherit = 'account.payment.group'

	cuota_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota')

class ExtendsAccountMoveLine(models.Model):
	_name = 'account.move.line'
	_inherit = 'account.move.line'

	cuota_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota')
	cuota_descuento_id = fields.Many2one('financiera.prestamo.cuota', 'Cuota')


class ExtendsAccountMoveLine(models.Model):
	_name = 'account.debt.line'
	_inherit = 'account.debt.line'

	_order = 'date desc, id desc'