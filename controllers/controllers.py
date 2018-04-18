# -*- coding: utf-8 -*-
from openerp import http

# class FinancieraPrestamos(http.Controller):
#     @http.route('/financiera_prestamos/financiera_prestamos/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/financiera_prestamos/financiera_prestamos/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('financiera_prestamos.listing', {
#             'root': '/financiera_prestamos/financiera_prestamos',
#             'objects': http.request.env['financiera_prestamos.financiera_prestamos'].search([]),
#         })

#     @http.route('/financiera_prestamos/financiera_prestamos/objects/<model("financiera_prestamos.financiera_prestamos"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('financiera_prestamos.object', {
#             'object': obj
#         })