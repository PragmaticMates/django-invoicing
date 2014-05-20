from decimal import Decimal


def import_name(name):
    components = name.split('.')
    mod = __import__('.'.join(components[0:-1]), globals(), locals(), [components[-1]])
    return getattr(mod, components[-1])


def round_to_two_places(value):
    return Decimal(value).quantize(Decimal(10) ** -2)
