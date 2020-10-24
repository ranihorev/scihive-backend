from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def __init__(self, *args, **kwargs):
        rename_fields = kwargs.pop('rename_fields', {})
        super(CustomJsonFormatter, self).__init__(*args, **kwargs,
                                                  rename_fields={**rename_fields, 'levelname': 'severity'})
