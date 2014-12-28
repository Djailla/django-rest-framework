"""
Helper functions for mapping model fields to a dictionary of default
keyword arguments that should be used for their equivelent serializer fields.
"""
from django.core import validators
from django.db import models
from django.utils.text import capfirst
from rest_framework.compat import clean_manytomany_helptext
from rest_framework.validators import UniqueValidator
import inspect


class ClassLookupDict(object):
    """
    Takes a dictionary with classes as keys.
    Lookups against this object will traverses the object's inheritance
    hierarchy in method resolution order, and returns the first matching value
    from the dictionary or raises a KeyError if nothing matches.
    """
    def __init__(self, mapping):
        self.mapping = mapping

    def __getitem__(self, key):
        if hasattr(key, '_proxy_class'):
            # Deal with proxy classes. Ie. BoundField behaves as if it
            # is a Field instance when using ClassLookupDict.
            base_class = key._proxy_class
        else:
            base_class = key.__class__

        for cls in inspect.getmro(base_class):
            if cls in self.mapping:
                return self.mapping[cls]
        raise KeyError('Class %s not found in lookup.', cls.__name__)


def needs_label(model_field, field_name):
    """
    Returns `True` if the label based on the model's verbose name
    is not equal to the default label it would have based on it's field name.
    """
    default_label = field_name.replace('_', ' ').capitalize()
    return capfirst(model_field.verbose_name) != default_label


def get_detail_view_name(model):
    """
    Given a model class, return the view name to use for URL relationships
    that refer to instances of the model.
    """
    return '%(model_name)s-detail' % {
        'app_label': model._meta.app_label,
        'model_name': model._meta.object_name.lower()
    }


def get_field_kwargs(field_name, model_field):
    """
    Creates a default instance of a basic non-relational field.
    """
    kwargs = {}
    validator_kwarg = list(model_field.validators)

    # The following will only be used by ModelField classes.
    # Gets removed for everything else.
    kwargs['model_field'] = model_field

    if model_field.verbose_name and needs_label(model_field, field_name):
        kwargs['label'] = capfirst(model_field.verbose_name)

    if model_field.help_text:
        kwargs['help_text'] = model_field.help_text

    max_digits = getattr(model_field, 'max_digits', None)
    if max_digits is not None:
        kwargs['max_digits'] = max_digits

    decimal_places = getattr(model_field, 'decimal_places', None)
    if decimal_places is not None:
        kwargs['decimal_places'] = decimal_places

    if isinstance(model_field, models.TextField):
        kwargs['style'] = {'base_template': 'textarea.html'}

    if isinstance(model_field, models.AutoField) or not model_field.editable:
        # If this field is read-only, then return early.
        # Further keyword arguments are not valid.
        kwargs['read_only'] = True
        return kwargs

    if model_field.has_default() or model_field.blank or model_field.null:
        kwargs['required'] = False

    if model_field.null and not isinstance(model_field, models.NullBooleanField):
        kwargs['allow_null'] = True

    if model_field.blank:
        kwargs['allow_blank'] = True

    if model_field.flatchoices:
        # If this model field contains choices, then return early.
        # Further keyword arguments are not valid.
        kwargs['choices'] = model_field.flatchoices
        return kwargs

    # Ensure that max_length is passed explicitly as a keyword arg,
    # rather than as a validator.
    max_length = getattr(model_field, 'max_length', None)
    if max_length is not None and isinstance(model_field, models.CharField):
        kwargs['max_length'] = max_length
        validator_kwarg = [
            validator for validator in validator_kwarg
            if not isinstance(validator, validators.MaxLengthValidator)
        ]

    # Ensure that min_length is passed explicitly as a keyword arg,
    # rather than as a validator.
    min_length = next((
        validator.limit_value for validator in validator_kwarg
        if isinstance(validator, validators.MinLengthValidator)
    ), None)
    if min_length is not None:
        kwargs['min_length'] = min_length
        validator_kwarg = [
            validator for validator in validator_kwarg
            if not isinstance(validator, validators.MinLengthValidator)
        ]

    # Ensure that max_value is passed explicitly as a keyword arg,
    # rather than as a validator.
    max_value = next((
        validator.limit_value for validator in validator_kwarg
        if isinstance(validator, validators.MaxValueValidator)
    ), None)
    if max_value is not None:
        kwargs['max_value'] = max_value
        validator_kwarg = [
            validator for validator in validator_kwarg
            if not isinstance(validator, validators.MaxValueValidator)
        ]

    # Ensure that max_value is passed explicitly as a keyword arg,
    # rather than as a validator.
    min_value = next((
        validator.limit_value for validator in validator_kwarg
        if isinstance(validator, validators.MinValueValidator)
    ), None)
    if min_value is not None:
        kwargs['min_value'] = min_value
        validator_kwarg = [
            validator for validator in validator_kwarg
            if not isinstance(validator, validators.MinValueValidator)
        ]

    # URLField does not need to include the URLValidator argument,
    # as it is explicitly added in.
    if isinstance(model_field, models.URLField):
        validator_kwarg = [
            validator for validator in validator_kwarg
            if not isinstance(validator, validators.URLValidator)
        ]

    # EmailField does not need to include the validate_email argument,
    # as it is explicitly added in.
    if isinstance(model_field, models.EmailField):
        validator_kwarg = [
            validator for validator in validator_kwarg
            if validator is not validators.validate_email
        ]

    # SlugField do not need to include the 'validate_slug' argument,
    if isinstance(model_field, models.SlugField):
        validator_kwarg = [
            validator for validator in validator_kwarg
            if validator is not validators.validate_slug
        ]

    if getattr(model_field, 'unique', False):
        validator = UniqueValidator(queryset=model_field.model._default_manager)
        validator_kwarg.append(validator)

    if validator_kwarg:
        kwargs['validators'] = validator_kwarg

    return kwargs


def get_relation_kwargs(field_name, relation_info):
    """
    Creates a default instance of a flat relational field.
    """
    model_field, related_model, to_many, has_through_model = relation_info
    kwargs = {
        'queryset': related_model._default_manager,
        'view_name': get_detail_view_name(related_model)
    }

    if to_many:
        kwargs['many'] = True

    if has_through_model:
        kwargs['read_only'] = True
        kwargs.pop('queryset', None)

    if model_field:
        if model_field.verbose_name and needs_label(model_field, field_name):
            kwargs['label'] = capfirst(model_field.verbose_name)
        help_text = clean_manytomany_helptext(model_field.help_text)
        if help_text:
            kwargs['help_text'] = help_text
        if not model_field.editable:
            kwargs['read_only'] = True
            kwargs.pop('queryset', None)
        if kwargs.get('read_only', False):
            # If this field is read-only, then return early.
            # No further keyword arguments are valid.
            return kwargs
        if model_field.has_default() or model_field.null:
            kwargs['required'] = False
        if model_field.null:
            kwargs['allow_null'] = True
        if model_field.validators:
            kwargs['validators'] = model_field.validators
        if getattr(model_field, 'unique', False):
            validator = UniqueValidator(queryset=model_field.model._default_manager)
            kwargs['validators'] = kwargs.get('validators', []) + [validator]

    return kwargs


def get_nested_relation_kwargs(relation_info):
    kwargs = {'read_only': True}
    if relation_info.to_many:
        kwargs['many'] = True
    return kwargs


def get_url_kwargs(model_field):
    return {
        'view_name': get_detail_view_name(model_field)
    }