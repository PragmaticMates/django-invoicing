# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):

        # Changing field 'Invoice.language'
        db.alter_column('invoicing_invoices', 'language', self.gf('django.db.models.fields.CharField')(max_length=10))

    def backwards(self, orm):

        # Changing field 'Invoice.language'
        db.alter_column('invoicing_invoices', 'language', self.gf('django.db.models.fields.CharField')(max_length=2))

    models = {
        u'invoicing.invoice': {
            'Meta': {'ordering': "('date_issue', 'number')", 'object_name': 'Invoice', 'db_table': "'invoicing_invoices'"},
            'bank_city': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'bank_country': ('django_countries.fields.CountryField', [], {'default': 'None', 'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'bank_iban': ('django_iban.fields.IBANField', [], {'default': 'None', 'max_length': '34'}),
            'bank_name': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'bank_street': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'bank_swift_bic': ('django_iban.fields.SWIFTBICField', [], {'default': 'None', 'max_length': '11'}),
            'bank_zip': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'constant_symbol': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '64', 'null': 'True', 'blank': 'True'}),
            'created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            'credit': ('django.db.models.fields.DecimalField', [], {'default': '0', 'max_digits': '10', 'decimal_places': '2'}),
            'currency': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'customer_additional_info': ('jsonfield.fields.JSONField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'customer_city': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'customer_country': ('django_countries.fields.CountryField', [], {'max_length': '2'}),
            'customer_name': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'customer_registration_id': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'customer_street': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'customer_tax_id': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'customer_vat_id': ('invoicing.fields.VATField', [], {'default': 'None', 'max_length': '13', 'null': 'True', 'blank': 'True'}),
            'customer_zip': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'date_due': ('django.db.models.fields.DateField', [], {}),
            'date_issue': ('django.db.models.fields.DateField', [], {}),
            'date_sent': ('model_utils.fields.MonitorField', [], {'default': 'None', 'null': 'True', u'monitor': "'status'", 'blank': 'True'}),
            'date_tax_point': ('django.db.models.fields.DateField', [], {}),
            'delivery_method': ('django.db.models.fields.CharField', [], {'default': "'PERSONAL_PICKUP'", 'max_length': '64'}),
            'discount': ('django.db.models.fields.DecimalField', [], {'default': '0', 'max_digits': '3', 'decimal_places': '1'}),
            'full_number': ('django.db.models.fields.CharField', [], {'max_length': '128', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'issuer_email': ('django.db.models.fields.EmailField', [], {'default': 'None', 'max_length': '75', 'null': 'True', 'blank': 'True'}),
            'issuer_name': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'issuer_phone': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'language': ('django.db.models.fields.CharField', [], {'max_length': '10'}),
            'modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'note': ('django.db.models.fields.CharField', [], {'default': "u'Thank you for using our services.'", 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'number': ('django.db.models.fields.IntegerField', [], {'db_index': 'True', 'blank': 'True'}),
            'payment_method': ('django.db.models.fields.CharField', [], {'max_length': '64'}),
            'reference': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '140', 'null': 'True', 'blank': 'True'}),
            'shipping_city': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'shipping_country': ('django_countries.fields.CountryField', [], {'default': 'None', 'max_length': '2', 'null': 'True', 'blank': 'True'}),
            'shipping_name': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'shipping_street': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'shipping_zip': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'specific_symbol': ('django.db.models.fields.PositiveIntegerField', [], {'default': 'None', 'max_length': '10', 'null': 'True', 'blank': 'True'}),
            'status': ('django.db.models.fields.CharField', [], {'default': "'NEW'", 'max_length': '64'}),
            'subtitle': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'supplier_additional_info': ('jsonfield.fields.JSONField', [], {'default': 'None', 'null': 'True', 'blank': 'True'}),
            'supplier_city': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'supplier_country': ('django_countries.fields.CountryField', [], {'default': 'None', 'max_length': '2'}),
            'supplier_name': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255'}),
            'supplier_registration_id': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'supplier_street': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'supplier_tax_id': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'supplier_vat_id': ('invoicing.fields.VATField', [], {'default': 'None', 'max_length': '13', 'null': 'True', 'blank': 'True'}),
            'supplier_zip': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '255', 'null': 'True', 'blank': 'True'}),
            'type': ('django.db.models.fields.CharField', [], {'default': "'INVOICE'", 'max_length': '64'}),
            'variable_symbol': ('django.db.models.fields.PositiveIntegerField', [], {'default': 'None', 'max_length': '10', 'null': 'True', 'blank': 'True'})
        },
        u'invoicing.item': {
            'Meta': {'ordering': "('-invoice', 'weight', 'created')", 'object_name': 'Item', 'db_table': "'invoicing_items'"},
            'created': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'invoice': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['invoicing.Invoice']"}),
            'modified': ('django.db.models.fields.DateTimeField', [], {'auto_now': 'True', 'blank': 'True'}),
            'quantity': ('django.db.models.fields.DecimalField', [], {'default': '1', 'max_digits': '10', 'decimal_places': '3'}),
            'tag': ('django.db.models.fields.CharField', [], {'default': 'None', 'max_length': '128', 'null': 'True', 'blank': 'True'}),
            'tax_rate': ('django.db.models.fields.DecimalField', [], {'default': 'None', 'null': 'True', 'max_digits': '3', 'decimal_places': '1', 'blank': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'unit': ('django.db.models.fields.CharField', [], {'default': "'PIECES'", 'max_length': '64'}),
            'unit_price': ('django.db.models.fields.DecimalField', [], {'max_digits': '10', 'decimal_places': '2'}),
            'weight': ('django.db.models.fields.IntegerField', [], {'default': '0', 'null': 'True', 'blank': 'True'})
        }
    }

    complete_apps = ['invoicing']