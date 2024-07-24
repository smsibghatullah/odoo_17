from odoo import api, fields, models

from odoo.exceptions import UserError
from itertools import groupby
from operator import itemgetter
from datetime import date

import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    """
    NOTES
    1. Fields with name starting with 'pos_' are removed from the vals before super call to `create`.
       Values of these fields are written to `pos_config_id` record after the super call.
       This is done so that these fields are written at the same time to the active pos.config record.
    2. During `creation` of this record, each related field is written to the source record
       *one after the other*, so constraints on the source record that are based on multiple
       fields might not work properly. However, only the *modified* related fields are written
       to the source field. But the identification of modified fields happen during the super
       call, not before `create` is called. Because of this, vals contains a lot of field before
       super call, then the number of fields is reduced after.
    """
    _inherit = 'res.config.settings'

    pos_stock_quant_id = fields.Many2one('stock.location', string='Location')



class ProductProduct(models.Model):
    _inherit = 'product.product'

    def get_product_info_pos(self, price, quantity, pos_config_id):
        self.ensure_one()
        config = self.env['pos.config'].browse(pos_config_id)
        stock_quants = self.env['stock.quant'].search([
                ('product_id', '=', self.id),
            ])

        locations = [{
        'location_id': quant.location_id.complete_name,
        'inventory_quantity': quant.inventory_quantity_auto_apply,
         } for quant in stock_quants]
        print(locations,"wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww")


        # Tax related
        taxes = self.taxes_id.compute_all(price, config.currency_id, quantity, self)
        grouped_taxes = {}
        for tax in taxes['taxes']:
            if tax['id'] in grouped_taxes:
                grouped_taxes[tax['id']]['amount'] += tax['amount']/quantity if quantity else 0
            else:
                grouped_taxes[tax['id']] = {
                    'name': tax['name'],
                    'amount': tax['amount']/quantity if quantity else 0
                }

        all_prices = {
            'price_without_tax': taxes['total_excluded']/quantity if quantity else 0,
            'price_with_tax': taxes['total_included']/quantity if quantity else 0,
            'tax_details': list(grouped_taxes.values()),
        }

        # Pricelists
        if config.use_pricelist:
            pricelists = config.available_pricelist_ids
        else:
            pricelists = config.pricelist_id
        price_per_pricelist_id = pricelists._price_get(self, quantity) if pricelists else False
        pricelist_list = [{'name': pl.name, 'price': price_per_pricelist_id[pl.id]} for pl in pricelists]

        # Warehouses
        warehouse_list = [
            {'name': w.name,
            'available_quantity': self.with_context({'warehouse': w.id}).qty_available,
            'forecasted_quantity': self.with_context({'warehouse': w.id}).virtual_available,
            'uom': self.uom_name}
            for w in self.env['stock.warehouse'].search([])]

        # Suppliers
        key = itemgetter('partner_id')
        supplier_list = []
        for key, group in groupby(sorted(self.seller_ids, key=key), key=key):
            for s in list(group):
                if not((s.date_start and s.date_start > date.today()) or (s.date_end and s.date_end < date.today()) or (s.min_qty > quantity)):
                    supplier_list.append({
                        'name': s.partner_id.name,
                        'delay': s.delay,
                        'price': s.price
                    })
                    break

        # Variants
        variant_list = [{'name': attribute_line.attribute_id.name,
                         'values': list(map(lambda attr_name: {'name': attr_name, 'search': '%s %s' % (self.name, attr_name)}, attribute_line.value_ids.mapped('name')))}
                        for attribute_line in self.attribute_line_ids]

        return {
            'all_prices': all_prices,
            'pricelists': pricelist_list,
            'warehouses': warehouse_list,
            'suppliers': supplier_list,
            'variants': variant_list,
            'locations': locations 
        }

