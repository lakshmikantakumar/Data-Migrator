"""Typed field-value transformations used by the GMF migration engine.

Each configured field rule is represented by its own transformer class.  The
module has no ArcPy dependency: it converts values and leaves cursor handling,
schema operations, and feature insertion to ``migrator.py``.
"""

from __future__ import annotations

import ast
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Type

try:
    from .rules import FieldRule, FieldRuleName
    from .utils.exception_utils import MigrationError
except ImportError:  # pragma: no cover - ArcGIS top-level toolbox imports.
    from rules import FieldRule, FieldRuleName  # type: ignore
    from utils.exception_utils import MigrationError  # type: ignore


_FIELD_TOKEN = re.compile(r"!([^!]+)!")
_ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left ** right,
}
_ALLOWED_UNARY_OPERATORS = {ast.USub: lambda value: -value, ast.UAdd: lambda value: +value, ast.Not: lambda value: not value}
_ALLOWED_COMPARISON_OPERATORS = {
    ast.Eq: lambda left, right: left == right, ast.NotEq: lambda left, right: left != right,
    ast.Lt: lambda left, right: left < right, ast.LtE: lambda left, right: left <= right,
    ast.Gt: lambda left, right: left > right, ast.GtE: lambda left, right: left >= right,
}


@dataclass(frozen=True)
class TransformResult:
    """Result of applying a field transformation.

    Args:
        assign: Whether migrator should assign a target-field value.
        value: Transformed value when assign is true.

    Raises:
        None.

    Notes:
        IGNORE returns ``assign=False`` rather than a magic value.
    """

    assign: bool
    value: Any = None


@dataclass(frozen=True)
class TransformContext:
    """Read-only values and mapping tables available to field transformations.

    Args:
        source_row: Source cursor row keyed by source field name.
        domain_mappings: Named source-to-target domain mappings.
        lookup_tables: Named source-to-target lookup mappings.
        concat_separator: Default separator for CONCAT values.

    Raises:
        None.

    Notes:
        Mapping names and source-field names are resolved case-insensitively.
    """

    source_row: Mapping[str, Any] = field(default_factory=dict)
    domain_mappings: Mapping[str, Mapping[Any, Any]] = field(default_factory=dict)
    lookup_tables: Mapping[str, Mapping[Any, Any]] = field(default_factory=dict)
    concat_separator: str = ""

    def value_for(self, field_name: str) -> Any:
        """Return one source-row field value using case-insensitive matching.

        Args:
            field_name: Requested source field name.

        Returns:
            Source value.

        Raises:
            MigrationError: If the source field is unavailable.

        Notes:
            This accommodates casing differences among geodatabase backends.
        """
        for name, value in self.source_row.items():
            if name.casefold() == field_name.casefold():
                return value
        raise MigrationError("Source field is unavailable for transformation: {}".format(field_name))

    def mapping_for(self, name: str, lookup: bool) -> Mapping[Any, Any]:
        """Return a configured domain or lookup mapping by name.

        Args:
            name: Domain or lookup mapping name.
            lookup: Whether to retrieve from lookup tables rather than domains.

        Returns:
            Requested mapping table.

        Raises:
            MigrationError: If the named mapping is unavailable.

        Notes:
            The returned mapping is not changed by transformation classes.
        """
        mappings = self.lookup_tables if lookup else self.domain_mappings
        for mapping_name, mapping in mappings.items():
            if mapping_name.casefold() == name.casefold():
                return mapping
        kind = "lookup" if lookup else "domain"
        raise MigrationError("{} mapping is unavailable: {}".format(kind.capitalize(), name))


class FieldTransformer:
    """Abstract base class for one configured field transformation rule."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Transform a source value into an assignment result.

        Args:
            value: Source value selected by the migration engine.
            rule: Typed field rule being applied.
            context: Source-row values and configured mappings.

        Returns:
            TransformResult for the target field.

        Raises:
            NotImplementedError: Always in the abstract base class.

        Notes:
            Subclasses must remain pure and must not perform ArcPy operations.
        """
        raise NotImplementedError


class CopyTransformer(FieldTransformer):
    """Return the source value unchanged for COPY."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply COPY.

        Args:
            value: Source value.
            rule: COPY field rule.
            context: Transformation context.

        Returns:
            Assignable result containing value unchanged.

        Raises:
            None.

        Notes:
            ArcPy field-type coercion is left to the target InsertCursor.
        """
        return TransformResult(True, value)


class DomainTransformer(FieldTransformer):
    """Translate a source value through a named domain mapping."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply DOMAIN using rule.parameter as the mapping name.

        Args:
            value: Source domain code.
            rule: DOMAIN field rule.
            context: Transformation context.

        Returns:
            Assignable mapped target code.

        Raises:
            MigrationError: If mapping name or source code is unavailable.

        Notes:
            String-key fallback preserves CSV-coded numeric values.
        """
        mapping_name = _required_parameter(rule)
        return TransformResult(True, _mapping_value(context.mapping_for(mapping_name, lookup=False), value, "domain", mapping_name))


class DefaultTransformer(FieldTransformer):
    """Return the configured Default_Value for DEFAULT."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply DEFAULT.

        Args:
            value: Ignored source value.
            rule: DEFAULT field rule.
            context: Transformation context.

        Returns:
            Assignable configured default value.

        Raises:
            MigrationError: If Default_Value is missing.

        Notes:
            Default text remains uncoerced for ArcPy target-field conversion.
        """
        if rule.default_value is None:
            raise MigrationError("DEFAULT rule requires Default_Value for {}.".format(rule.target_field))
        return TransformResult(True, rule.default_value)


class UUIDTransformer(FieldTransformer):
    """Generate a brace-wrapped uppercase UUID for UUID."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply UUID.

        Args:
            value: Ignored source value.
            rule: UUID field rule.
            context: Transformation context.

        Returns:
            Assignable UUID string.

        Raises:
            None.

        Notes:
            The output matches common ArcGIS GlobalID textual representation.
        """
        return TransformResult(True, "{" + str(uuid.uuid4()).upper() + "}")


class LookupTransformer(FieldTransformer):
    """Translate a source value through a named lookup table."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply LOOKUP using rule.parameter as the lookup name.

        Args:
            value: Source lookup key.
            rule: LOOKUP field rule.
            context: Transformation context.

        Returns:
            Assignable lookup value.

        Raises:
            MigrationError: If lookup name or source value is unavailable.

        Notes:
            Lookup tables are supplied by the migration layer, not read here.
        """
        lookup_name = _required_parameter(rule)
        return TransformResult(True, _mapping_value(context.mapping_for(lookup_name, lookup=True), value, "lookup", lookup_name))


class ExpressionTransformer(FieldTransformer):
    """Evaluate a restricted field expression for EXPRESSION."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply EXPRESSION using ArcGIS-style ``!Field!`` references.

        Args:
            value: Primary source value, available as ``value`` in expression.
            rule: EXPRESSION field rule.
            context: Transformation context.

        Returns:
            Assignable expression result.

        Raises:
            MigrationError: If expression syntax or operation is unsafe/invalid.

        Notes:
            The expression evaluator intentionally does not allow imports,
            attribute traversal, arbitrary calls, or Python eval.
        """
        return TransformResult(True, _evaluate_expression(_required_parameter(rule), value, context))


class ConcatTransformer(FieldTransformer):
    """Join named source fields for CONCAT."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply CONCAT with comma-separated field names in Parameter.

        Args:
            value: Primary source value when Parameter is blank.
            rule: CONCAT field rule.
            context: Transformation context.

        Returns:
            Assignable joined text.

        Raises:
            MigrationError: If a named source field is unavailable.

        Notes:
            A Parameter such as ``NAME,TYPE`` joins values with concat_separator.
        """
        fields = _split_parameter(rule.parameter)
        values = [context.value_for(name) for name in fields] if fields else [value]
        return TransformResult(True, context.concat_separator.join("" if item is None else str(item) for item in values))


class SplitTransformer(FieldTransformer):
    """Select one delimited fragment from a value for SPLIT."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply SPLIT with ``delimiter|index`` Parameter syntax.

        Args:
            value: Source text to split.
            rule: SPLIT field rule.
            context: Transformation context.

        Returns:
            Assignable selected fragment.

        Raises:
            MigrationError: If Parameter is invalid or index is unavailable.

        Notes:
            Omitting index selects the first fragment; index is zero-based.
        """
        delimiter, index = _split_specification(_required_parameter(rule))
        parts = "" if value is None else str(value)
        fragments = parts.split(delimiter)
        try:
            return TransformResult(True, fragments[index])
        except IndexError as error:
            raise MigrationError("SPLIT index {} is unavailable for value {!r}.".format(index, value)) from error


class SubstringTransformer(FieldTransformer):
    """Extract a character range from a text value for SUBSTRING."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply SUBSTRING with ``start,length`` Parameter syntax.

        Args:
            value: Source text value.
            rule: SUBSTRING field rule.
            context: Transformation context.

        Returns:
            Assignable substring.

        Raises:
            MigrationError: If Parameter is invalid.

        Notes:
            A negative start follows normal Python slicing semantics.
        """
        start, length = _substring_specification(_required_parameter(rule))
        text = "" if value is None else str(value)
        return TransformResult(True, text[start:] if length is None else text[start:start + length])


class DateFormatTransformer(FieldTransformer):
    """Parse and reformat dates for DATEFORMAT."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply DATEFORMAT with ``input_format|output_format`` Parameter syntax.

        Args:
            value: Source date, datetime, or formatted date text.
            rule: DATEFORMAT field rule.
            context: Transformation context.

        Returns:
            Assignable output date text.

        Raises:
            MigrationError: If format specification or input date is invalid.

        Notes:
            Native date/datetime values do not require an input format.
        """
        input_format, output_format = _date_format_specification(_required_parameter(rule))
        if isinstance(value, (datetime, date)):
            parsed = value
        else:
            try:
                parsed = datetime.strptime(str(value), input_format)
            except (TypeError, ValueError) as error:
                raise MigrationError("DATEFORMAT cannot parse {!r} using {!r}.".format(value, input_format)) from error
        return TransformResult(True, parsed.strftime(output_format))


class CalculateTransformer(ExpressionTransformer):
    """Evaluate a restricted arithmetic calculation for CALCULATE."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply CALCULATE using the same safe expression grammar as EXPRESSION.

        Args:
            value: Primary source value, available as ``value``.
            rule: CALCULATE field rule.
            context: Transformation context.

        Returns:
            Assignable calculation result.

        Raises:
            MigrationError: If the calculation is unsafe or invalid.

        Notes:
            CALCULATE remains a separate class to keep configuration behavior
            explicit even though it shares the restricted evaluator.
        """
        return TransformResult(True, _evaluate_expression(_required_parameter(rule), value, context))


class IgnoreTransformer(FieldTransformer):
    """Return a non-assignment result for IGNORE."""

    def transform(self, value: Any, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply IGNORE.

        Args:
            value: Ignored source value.
            rule: IGNORE field rule.
            context: Transformation context.

        Returns:
            Non-assignment TransformResult.

        Raises:
            None.

        Notes:
            Migrator must omit this target field from its InsertCursor row.
        """
        return TransformResult(False)


_TRANSFORMERS: Mapping[FieldRuleName, Type[FieldTransformer]] = {
    FieldRuleName.COPY: CopyTransformer, FieldRuleName.DOMAIN: DomainTransformer,
    FieldRuleName.DEFAULT: DefaultTransformer, FieldRuleName.UUID: UUIDTransformer,
    FieldRuleName.LOOKUP: LookupTransformer, FieldRuleName.EXPRESSION: ExpressionTransformer,
    FieldRuleName.CONCAT: ConcatTransformer, FieldRuleName.SPLIT: SplitTransformer,
    FieldRuleName.SUBSTRING: SubstringTransformer, FieldRuleName.DATEFORMAT: DateFormatTransformer,
    FieldRuleName.CALCULATE: CalculateTransformer, FieldRuleName.IGNORE: IgnoreTransformer,
}


class TransformEngine:
    """Select and execute the class corresponding to a typed FieldRule."""

    def transform(self, rule: FieldRule, context: TransformContext) -> TransformResult:
        """Apply one configured field rule to context source data.

        Args:
            rule: Typed FieldRule to execute.
            context: Source-row data and reusable mapping tables.

        Returns:
            TransformResult for the rule's target field.

        Raises:
            MigrationError: If a required source value or transformation fails.

        Notes:
            Disabled and IGNORE rules return non-assignment results.
        """
        if not rule.enabled or rule.rule is FieldRuleName.IGNORE:
            return IgnoreTransformer().transform(None, rule, context)
        value = context.value_for(rule.source_field) if rule.source_field else None
        transformer = _TRANSFORMERS[rule.rule]()
        try:
            return transformer.transform(value, rule, context)
        except MigrationError:
            raise
        except Exception as error:
            raise MigrationError("Field rule {} for {} failed: {}".format(rule.rule.value, rule.target_field, error)) from error


def transform_value(rule: FieldRule, source_row: Mapping[str, Any], domain_mappings: Optional[Mapping[str, Mapping[Any, Any]]] = None, lookup_tables: Optional[Mapping[str, Mapping[Any, Any]]] = None, concat_separator: str = "") -> TransformResult:
    """Convenience function to apply one FieldRule to a source-row mapping.

    Args:
        rule: Typed field rule.
        source_row: Current source feature values keyed by field name.
        domain_mappings: Optional named domain translation tables.
        lookup_tables: Optional named lookup translation tables.
        concat_separator: Separator used by CONCAT.

    Returns:
        TransformResult from the selected rule class.

    Raises:
        MigrationError: If transformation cannot be completed safely.

    Notes:
        This is suitable for unit tests and per-row migration processing.
    """
    context = TransformContext(source_row, domain_mappings or {}, lookup_tables or {}, concat_separator)
    return TransformEngine().transform(rule, context)


def _required_parameter(rule: FieldRule) -> str:
    """Return a required FieldRule Parameter value.

    Args:
        rule: Field rule whose parameter is required.

    Returns:
        Non-empty parameter text.

    Raises:
        MigrationError: If Parameter is blank.

    Notes:
        Central validation keeps transformer behavior consistent.
    """
    if not rule.parameter:
        raise MigrationError("{} rule requires Parameter for target field {}.".format(rule.rule.value, rule.target_field))
    return rule.parameter


def _mapping_value(mapping: Mapping[Any, Any], value: Any, kind: str, name: str) -> Any:
    """Return a mapping value with a string-key fallback.

    Args:
        mapping: Domain or lookup mapping.
        value: Source key to translate.
        kind: Mapping type used in error text.
        name: Mapping name used in error text.

    Returns:
        Mapped target value.

    Raises:
        MigrationError: If source key has no mapping.

    Notes:
        String fallback lets CSV code ``"01"`` match a cursor text value.
    """
    if value in mapping:
        return mapping[value]
    for source_value, target_value in mapping.items():
        if str(source_value) == str(value):
            return target_value
    raise MigrationError("{} mapping {} has no value for {!r}.".format(kind.capitalize(), name, value))


def _split_parameter(parameter: Optional[str]) -> Tuple[str, ...]:
    """Parse comma-separated CONCAT source-field names.

    Args:
        parameter: Optional comma-separated field-name list.

    Returns:
        Non-empty field-name tuple, or empty tuple.

    Raises:
        None.

    Notes:
        Blank parameter makes CONCAT operate on the primary source value.
    """
    return tuple(item.strip() for item in (parameter or "").split(",") if item.strip())


def _split_specification(parameter: str) -> Tuple[str, int]:
    """Parse SPLIT ``delimiter|index`` text.

    Args:
        parameter: Required split specification.

    Returns:
        Delimiter and zero-based index.

    Raises:
        MigrationError: If delimiter is blank or index is not an integer.

    Notes:
        An omitted index defaults to zero.
    """
    parts = parameter.split("|", 1)
    delimiter = parts[0]
    if not delimiter:
        raise MigrationError("SPLIT delimiter cannot be empty.")
    try:
        return delimiter, int(parts[1]) if len(parts) == 2 and parts[1].strip() else 0
    except ValueError as error:
        raise MigrationError("SPLIT index must be an integer: {}".format(parameter)) from error


def _substring_specification(parameter: str) -> Tuple[int, Optional[int]]:
    """Parse SUBSTRING ``start,length`` text.

    Args:
        parameter: Required substring specification.

    Returns:
        Start offset and optional length.

    Raises:
        MigrationError: If syntax or numeric values are invalid.

    Notes:
        A missing length means extract through the final character.
    """
    parts = [item.strip() for item in parameter.split(",")]
    if len(parts) not in (1, 2) or not parts[0]:
        raise MigrationError("SUBSTRING Parameter must be start or start,length.")
    try:
        length = int(parts[1]) if len(parts) == 2 and parts[1] else None
        if length is not None and length < 0:
            raise ValueError
        return int(parts[0]), length
    except ValueError as error:
        raise MigrationError("SUBSTRING Parameter must contain integer values: {}".format(parameter)) from error


def _date_format_specification(parameter: str) -> Tuple[str, str]:
    """Parse DATEFORMAT ``input_format|output_format`` text.

    Args:
        parameter: Required date format specification.

    Returns:
        Input and output strptime/strftime formats.

    Raises:
        MigrationError: If either format is absent.

    Notes:
        Percent directives follow Python datetime conventions.
    """
    parts = parameter.split("|", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise MigrationError("DATEFORMAT Parameter must be input_format|output_format.")
    return parts[0], parts[1]


def _evaluate_expression(expression: str, value: Any, context: TransformContext) -> Any:
    """Evaluate a restricted expression after replacing ArcGIS field tokens.

    Args:
        expression: Expression with optional ``!FIELD!`` references.
        value: Primary source value exposed as ``value``.
        context: Source-row lookup context.

    Returns:
        Expression value.

    Raises:
        MigrationError: If parsing or safe evaluation fails.

    Notes:
        Field tokens become generated local names before AST inspection.
    """
    locals_map: Dict[str, Any] = {"value": value}

    def replace_token(match: re.Match[str]) -> str:
        name = "field_{}".format(len(locals_map))
        locals_map[name] = context.value_for(match.group(1).strip())
        return name

    prepared = _FIELD_TOKEN.sub(replace_token, expression)
    try:
        tree = ast.parse(prepared, mode="eval")
        return _SafeExpressionEvaluator(locals_map).evaluate(tree.body)
    except MigrationError:
        raise
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as error:
        raise MigrationError("Invalid expression {!r}: {}".format(expression, error)) from error


class _SafeExpressionEvaluator:
    """Evaluate a deliberately narrow subset of Python expression AST nodes."""

    def __init__(self, locals_map: Mapping[str, Any]) -> None:
        """Create evaluator with fixed local values.

        Args:
            locals_map: Allowed expression names and their values.

        Returns:
            None.

        Raises:
            None.

        Notes:
            No globals, builtins, imports, or user functions are exposed.
        """
        self._locals = dict(locals_map)

    def evaluate(self, node: ast.AST) -> Any:
        """Evaluate one allowed AST node recursively.

        Args:
            node: Parsed expression node.

        Returns:
            Evaluated value.

        Raises:
            MigrationError: If the node or operation is disallowed.

        Notes:
            Supported operations cover numeric/string calculations in GMF CSVs.
        """
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self._locals:
                return self._locals[node.id]
            raise MigrationError("Expression name is not allowed: {}".format(node.id))
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
            return _ALLOWED_BINARY_OPERATORS[type(node.op)](self.evaluate(node.left), self.evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
            return _ALLOWED_UNARY_OPERATORS[type(node.op)](self.evaluate(node.operand))
        if isinstance(node, ast.BoolOp):
            values = [self.evaluate(value) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values) if isinstance(node.op, ast.Or) else self._unsupported(node)
        if isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            for operator, comparator in zip(node.ops, node.comparators):
                if type(operator) not in _ALLOWED_COMPARISON_OPERATORS:
                    return self._unsupported(node)
                right = self.evaluate(comparator)
                if not _ALLOWED_COMPARISON_OPERATORS[type(operator)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self.evaluate(node.body if self.evaluate(node.test) else node.orelse)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.evaluate(item) for item in node.elts]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            functions = {"str": str, "int": int, "float": float, "abs": abs, "round": round, "len": len}
            if node.func.id in functions and not node.keywords:
                return functions[node.func.id](*(self.evaluate(argument) for argument in node.args))
        return self._unsupported(node)

    @staticmethod
    def _unsupported(node: ast.AST) -> Any:
        """Raise a consistent error for a prohibited expression construct.

        Args:
            node: Unsupported AST node.

        Returns:
            Never returns.

        Raises:
            MigrationError: Always.

        Notes:
            This is the security boundary preventing arbitrary code execution.
        """
        raise MigrationError("Expression construct is not allowed: {}".format(type(node).__name__))


__all__ = [
    "CalculateTransformer", "ConcatTransformer", "CopyTransformer", "DateFormatTransformer",
    "DefaultTransformer", "DomainTransformer", "ExpressionTransformer", "FieldTransformer",
    "IgnoreTransformer", "LookupTransformer", "SplitTransformer", "SubstringTransformer",
    "TransformContext", "TransformEngine", "TransformResult", "UUIDTransformer", "transform_value",
]
