# -*- coding: utf-8 -*-
{
    'name': "financiera_prestamos",

    'summary': """
        Manejo de prestamos
        """,

    'description': """
        Manejo de prestamos
    """,

    'author': "LIBRASOFT",
    'website': "http://libra-soft.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'finance',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account_accountant', 
                'l10n_ar_aeroo_payment_group', 
                'account_debt_management', 
                'account_statement_move_import', 
                'feriados','web_tree_many2one_clickable',
    ],

    # always loaded
    'data': [
        'security/user_groups.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'data/defaultdata.xml',
    ],
    # only loaded in demonstration mode
    #'demo': [
        #'demo/demo.xml',
    #],
}