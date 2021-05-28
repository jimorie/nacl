""" Exceptions and error handling. """

import functools

import click
import simpleeval


class ConfigSyntaxError(RuntimeError):
    """Exception raised when the config parser fails."""

    pass


def errorhandler(decorated):
    """
    Decorator for handling known exceptions in the decorated function by
    re-raising them as `click.ClickException`.
    """

    @functools.wraps(decorated)
    def decorator(*args, **kwargs):
        try:
            return decorated(*args, **kwargs)
        except SyntaxError as e:
            if e.text and e.offset:
                message = e.text + " " * (e.offset - 1) + "^"
            else:
                message = str(e)
            raise click.ClickException(f"Syntax error in filter:\n\n{message}")
        except simpleeval.InvalidExpression as e:
            message = getattr(e, "message", str(e))
            raise click.ClickException(message)
        except RuntimeError as e:
            raise click.ClickException(str(e))

    return decorator
