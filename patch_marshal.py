from collections import OrderedDict

import flask_restful


def marshal(data, fields, envelope=None):
    def make(cls):
        if isinstance(cls, type):
            return cls()
        return cls

    if isinstance(data, (list, tuple)):
        return (OrderedDict([(envelope, [marshal(d, fields) for d in data])])
                if envelope else [marshal(d, fields) for d in data])

    items = ((k, marshal(data, v) if isinstance(v, dict) else make(v).output(k, data)) for k, v in fields.items())
    # filtering None
    items = ((k, v) for k, v in items if v is not None)
    return OrderedDict([(envelope, OrderedDict(items))]) if envelope else OrderedDict(items)


flask_restful.marshal = marshal
