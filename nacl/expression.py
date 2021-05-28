""" Generic extensions to the simpleeval library. """

import ast
import collections
import typing as t

import simpleeval

from nacl.util import register_decorator


class register_operator(register_decorator):
    """
    Decorator for registering alternative operators to `Expression` objects.
    """

    pass


class register_function(register_decorator):
    """
    Decorator for registering additional functions to `Expression` objects.
    """

    pass


class Expression(simpleeval.EvalWithCompoundTypes):
    """
    Parsed expression that can be used repeatedly.

    `Expression` differs from the parent class `simpleeval.SimpleEval` in that
    the parsed expression is stored for repeated use with different named
    arguments.

    `Expression` also enables sub-classes to use the `register_operator` and
    `register_function` decorators on class methods to define custom operator
    behavior and new functions to be used in the evaluation of the
    expression.

    Examples:

        >>> Expression("1 + 1").eval()
        2

        >>> expr = Expression("foo + bar")
        >>> expr.eval({"foo": 1, "bar": 2})
        3

        >>> expr.eval({"foo": "a", "bar": "b"})
        'ab'

        >>> class PlusIsMinusExpression(Expression):
        ...     @register_operator(key=ast.Add)
        ...     def plusisminus(a, b):
        ...         return a - b
        >>> PlusIsMinusExpression("1 + 1").eval()
        0

        >>> class MyFuncExpression(Expression):
        ...     @register_function
        ...     def myfunc(arg):
        ...         return arg.split(",")
        >>> MyFuncExpression("myfunc(foo)").eval({"foo": "a,b,c"})
        ['a', 'b', 'c']
    """

    def __init__(self, expr: str):
        operators = simpleeval.DEFAULT_OPERATORS.copy()
        operators.update(register_operator.get_registered(self.__class__))
        functions = simpleeval.DEFAULT_FUNCTIONS.copy()
        functions.update(register_function.get_registered(self.__class__))
        super().__init__(operators=operators, functions=functions)
        self.expr = expr
        self.test = ast.parse(expr)

    def eval(self, names: t.Mapping = None) -> t.Any:
        """
        Evaluate the expression with the named values in `names` and return
        the resulting value.
        """
        self.names = collections.ChainMap(names or {}, simpleeval.DEFAULT_NAMES)
        self._max_count = 0
        return_value = True
        for node in self.test.body:
            return_value = self._eval(node)
        return return_value

    @property
    def dataobject(self) -> t.Mapping:
        """
        Return the original `names` mapping that was passed in to
        `Expression.eval`.
        """
        return self.names.maps[0]
