# -*- coding: utf-8 -*-

from odoo import fields, http
from odoo.http import request
from odoo.addons.portal.controllers import portal
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.addons.portal.controllers.mail import _message_post_helper

class SaleOrderPortal(portal.CustomerPortal):
	@http.route(['/my/orders/<int:order_id>/accept_order'], type='http', auth="public", website=True)
	def portal_order_accept(self, order_id, access_token=None, l10n_mx_edi_usage=False, l10n_mx_edi_payment_method_id=False, **kw):
		access_token = access_token or request.httprequest.args.get('access_token')
		try:
			order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
		except (AccessError, MissingError):
			return {'error': _('Invalid order.')}
		#try:
		l10n_mx_edi_payment_method_id = int(l10n_mx_edi_payment_method_id)
		order_sudo.write({
			'l10n_mx_edi_usage' : l10n_mx_edi_usage,
			'l10n_mx_edi_payment_method_id' : l10n_mx_edi_payment_method_id,
			'next_invoice_date' : fields.Date.today() if order_sudo.is_subscription else False,
		})
		l10n_mx_edi_payment_method_id = request.env['l10n_mx_edi.payment.method'].sudo().browse(l10n_mx_edi_payment_method_id)

		msg = "Datos de facturación elegidos por el cliente: <br/>Uso de CFDI: {}<br/>Forma de pago : {}".format(l10n_mx_edi_usage, l10n_mx_edi_payment_method_id.name)
		_message_post_helper(
			"sale.order",
			order_sudo.id,
			message=msg,
			token=access_token,
			message_type="notification",

			subtype_xmlid="mail.mt_note",
			partner_ids=order_sudo.user_id.sudo().partner_id.ids,
		)
		if order_sudo.partner_id.commercial_partner_id.credit_status == 'counted':
			request.env.cr.commit()
			move_id = order_sudo.with_context({'force_billing' : True})._create_invoices(final=True)
			move_id.with_context({'force_edi_process' : True}).action_post()
			redirect_url = move_id.sudo().get_portal_url()
		else:
			order_sudo.action_confirm()
			request.env.cr.commit()
			detailed_types = list(set(order_sudo.order_line.mapped('product_id.detailed_type')))
			if len(detailed_types) == 1:
				if detailed_types[0] == 'service':
					move_id = order_sudo._create_invoices(final=True)
					move_id.with_context({'force_edi_process' : True}).action_post()
					redirect_url = move_id.sudo().get_portal_url()
			redirect_url = order_sudo.get_portal_url()

		return request.redirect(redirect_url)
		#except Exception as e:
			#return {'error': e }

class WebsiteOrderPortal(WebsiteSale):

	def checkout_check_address(self, order):
		billing_fields_required = self._get_mandatory_fields_billing(order.partner_invoice_id.country_id.id)
		billing_fields_required = [x for x in billing_fields_required if x != "email"]
		billing_values = order.partner_invoice_id.read(billing_fields_required)[0].values()
		if not all(order.partner_invoice_id.read(billing_fields_required)[0].values()):
			return request.redirect('/shop/address?partner_id=%d' % order.partner_invoice_id.id)

		shipping_fields_required = self._get_mandatory_fields_shipping(order.partner_shipping_id.country_id.id)
		if not all(order.partner_shipping_id.read(shipping_fields_required)[0].values()):
			return request.redirect('/shop/address?partner_id=%d' % order.partner_shipping_id.id)

	@http.route('/shop/payment', type='http', auth='public', website=True, sitemap=False)
	def shop_payment(self, **post):
		order = request.website.sale_get_order()
		render_values = self._get_shop_payment_values(order, **post)
		render_values['only_services'] = order and order.only_services or False
		raise ValidationError('{}'.format(render_values))
