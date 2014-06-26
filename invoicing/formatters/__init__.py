class InvoiceFormatter(object):
    def __init__(self, invoice):
        self.invoice = invoice

    def get_response(self):
        raise NotImplementedError()
